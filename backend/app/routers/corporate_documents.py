"""Company-scoped corporate PDF APIs; all writes share the audit transaction."""
import json
import unicodedata
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Response
from urllib.parse import quote
from sqlalchemy.orm import Session, defer
from app.models.database import get_db
from app.models.compliance_company import ComplianceCompany, CompanyPermission
from app.models.employee import Employee
from app.models.corporate_document import CorporateDocument, CATEGORIES
from app.models.compliance_audit import audit_event
from app.routers.auth import require_compliance_access
from app.routers.compliance import _company_access, _rights

from fastapi.routing import APIRoute
from starlette.responses import JSONResponse

MAX_BODY_BYTES = 21 * 1024 * 1024  # PDF plus bounded multipart envelope/notes.


class BoundedCorporateRoute(APIRoute):
    async def handle(self, scope, receive, send):
        if scope['method'] != 'POST':
            return await super().handle(scope, receive, send)
        # Stage only a bounded request, BEFORE FastAPI's multipart parser can
        # spool anything. Never buffer/intercept a response. Count actual bytes
        # even with absent or dishonest Content-Length (e.g. chunked requests).
        lengths = [v for k, v in scope['headers'] if k.lower() == b'content-length']
        try:
            if len(lengths) > 1 or (lengths and (int(lengths[0]) < 0 or int(lengths[0]) > MAX_BODY_BYTES)):
                raise ValueError
        except ValueError:
            return await JSONResponse({'detail': 'Upload request must be at most 21 MiB'}, status_code=413)(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message['type'] == 'http.disconnect':
                return
            chunk = message.get('body', b'')
            if len(body) + len(chunk) > MAX_BODY_BYTES:
                return await JSONResponse({'detail': 'Upload request must be at most 21 MiB'}, status_code=413)(scope, receive, send)
            body.extend(chunk)
            if not message.get('more_body', False):
                break
        delivered = False
        async def replay():
            nonlocal delivered
            if delivered:
                return await receive()
            delivered = True
            return {'type': 'http.request', 'body': bytes(body), 'more_body': False}
        return await super().handle(scope, replay, send)


router = APIRouter(prefix='/api/compliance/companies/{company_id}/corporate-documents', tags=['corporate-documents'], route_class=BoundedCorporateRoute)

MAX_BYTES = 20 * 1024 * 1024
MAX_NOTES = 4000


async def validated_pdf(file, notes):
    name = (file.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
    name = ''.join(c for c in name if not unicodedata.category(c).startswith('C')).strip()
    if not name.lower().endswith('.pdf') or len(name) > 255 or file.content_type != 'application/pdf':
        raise HTTPException(400, 'A PDF filename and application/pdf content type are required')
    if len(notes) > MAX_NOTES:
        raise HTTPException(400, 'Notes must be 4000 characters or fewer')
    content = await file.read(MAX_BYTES + 1)
    if len(content) > MAX_BYTES:
        raise HTTPException(413, 'PDF must be at most 20 MiB')
    if not content.startswith(b'%PDF-'):
        raise HTTPException(400, 'Invalid PDF')
    from app.services.corporate_pdf import validate_pdf
    await validate_pdf(content)
    return name, content


def access(db, user, company_id, write=False):
    # Consistent order: Employee -> Company -> applicable Permission -> Document.
    # FOR SHARE (not KEY SHARE) conflicts with ordinary non-key UPDATE/DELETE
    # by existing admin routes, yet permits FK checks and concurrent readers.
    # Never write Company to acquire a lock: updated_at and all register fields
    # must remain untouched. Refresh cached identities after lock acquisition.
    employee = db.query(Employee).filter_by(timestation_id=user['timestation_id']).populate_existing().with_for_update(read=True).first()
    if employee is None or employee.login_enabled is False or employee.role not in ('admin', 'super_admin'):
        raise HTTPException(403, 'Account access changed; please sign in again')
    user.update(role=employee.role, name=employee.name, email=employee.email)
    company = db.query(ComplianceCompany).filter_by(id=company_id).populate_existing().with_for_update(read=True).first()
    if company is None:
        raise HTTPException(404, 'Company not found')
    editable = employee.role == 'super_admin'
    if not editable:
        permission = db.query(CompanyPermission).filter_by(employee_id=employee.timestation_id, company_id=company_id).populate_existing().with_for_update(read=True).first()
        if permission is None:
            raise HTTPException(403, 'Company access denied')
        editable = permission.can_edit
    if write and (not editable or not company.is_active):
        raise HTTPException(403, 'Company access denied or company archived')
    return company


def preliminary_access(db, user, company_id, write=False):
    # _company_access has a legacy lazy-creation branch for ID 1. Never enter it
    # for a missing company; this feature must never modify the company register.
    if db.get(ComplianceCompany, company_id) is None:
        raise HTTPException(404, 'Company not found')
    return _company_access(db, user, company_id, write=write)


def metadata(row):
    base = f'/api/compliance/companies/{row.company_id}/corporate-documents/{row.id}'
    return {**{key: getattr(row, key) for key in (
        'id', 'company_id', 'document_type', 'original_file_name', 'uploaded_by_user_id',
        'notes', 'status', 'replaced_document_id')},
        'uploaded_at': row.uploaded_at.isoformat(), 'view_url': base + '/view', 'download_url': base + '/download'}


def record_audit(db, user, company_id, action, old=None, new=None):
    # Allowlist identifiers and version metadata, never bytes, storage keys,
    # filenames or freeform notes (which may contain sensitive user input).
    fields = {'id', 'company_id', 'document_type', 'uploaded_by_user_id', 'uploaded_at', 'status', 'replaced_document_id'}
    def safe(value):
        return json.dumps({key: val for key, val in value.items() if key in fields}) if value is not None else None
    audit_event(db, user, company_id, None, 'corporate_document.' + action, safe(old), safe(new))


def document(db, company_id, document_id):
    row = db.query(CorporateDocument).filter_by(id=document_id, company_id=company_id).first()
    if row is None or row.status == 'deleted':
        raise HTTPException(404, 'Document not found')
    return row


def pdf_response(db, user, company_id, document_id, action):
    access(db, user, company_id)
    row = document(db, company_id, document_id)
    content, name = row.content, row.original_file_name
    try:
        record_audit(db, user, company_id, action, new=metadata(row))
        db.commit()  # Fail closed: never return bytes before the audit is durable.
    except Exception:
        db.rollback()
        raise
    disposition = 'inline' if action == 'view' else 'attachment'
    return Response(content, media_type='application/pdf', headers={
        'Cache-Control': 'private, no-store', 'Pragma': 'no-cache',
        'X-Content-Type-Options': 'nosniff',
        'Content-Disposition': f"{disposition}; filename=\"document.pdf\"; filename*=UTF-8''{quote(name, safe='')}",
    })


@router.get('/{document_id}/view')
def view_document(company_id: int, document_id: int, user=Depends(require_compliance_access), db: Session = Depends(get_db)):
    return pdf_response(db, user, company_id, document_id, 'view')


@router.get('/{document_id}/download')
def download_document(company_id: int, document_id: int, user=Depends(require_compliance_access), db: Session = Depends(get_db)):
    return pdf_response(db, user, company_id, document_id, 'download')


@router.post('/{document_id}/replace', status_code=201)
async def replace_document(company_id: int, document_id: int, file: UploadFile = File(...), notes: str = Form(''),
                           user=Depends(require_compliance_access), db: Session = Depends(get_db)):
    preliminary_access(db, user, company_id, write=True)
    old = document(db, company_id, document_id)
    if old.status != 'active':
        raise HTTPException(409, 'Only active documents may be replaced')
    db.rollback()  # Release preliminary transaction before untrusted validation.
    name, content = await validated_pdf(file, notes)
    access(db, user, company_id, write=True)
    old = document(db, company_id, document_id)
    if old.status != 'active':
        raise HTTPException(409, 'Only active documents may be replaced')
    before = metadata(old)
    try:
        # Compare-and-set prevents two replacements (or a concurrent delete)
        # from silently creating competing current versions.
        changed = db.query(CorporateDocument).filter_by(id=document_id, company_id=company_id, status='active').update(
            {'status': 'replaced'}, synchronize_session=False)
        if changed != 1:
            raise HTTPException(409, 'Document changed; reload and try again')
        row = CorporateDocument(company_id=company_id, document_type=old.document_type,
                                original_file_name=name, content=content, notes=notes,
                                uploaded_by_user_id=user['timestation_id'], replaced_document_id=old.id)
        db.add(row)
        db.flush()
        result = metadata(row)
        record_audit(db, user, company_id, 'replace', old=before, new=result)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'document': result}


@router.delete('/{document_id}', status_code=204)
def delete_document(company_id: int, document_id: int, user=Depends(require_compliance_access), db: Session = Depends(get_db)):
    access(db, user, company_id, write=True)
    row = document(db, company_id, document_id)
    before = metadata(row)
    try:
        changed = db.query(CorporateDocument).filter_by(id=document_id, company_id=company_id, status=row.status).update(
            {'status': 'deleted'}, synchronize_session=False)
        if changed != 1:
            raise HTTPException(409, 'Document changed; reload and try again')
        record_audit(db, user, company_id, 'delete', old=before, new={**before, 'status': 'deleted'})
        db.commit()
    except Exception:
        db.rollback()
        raise
    return Response(status_code=204)


@router.get('')
def list_documents(company_id: int, user=Depends(require_compliance_access), db: Session = Depends(get_db)):
    company = access(db, user, company_id)
    rows = db.query(CorporateDocument).options(defer(CorporateDocument.content)).filter(
        CorporateDocument.company_id == company_id, CorporateDocument.status != 'deleted').order_by(CorporateDocument.id.desc()).all()
    return {'documents': [metadata(row) for row in rows], 'categories': CATEGORIES,
            'can_edit': bool(company.is_active and _rights(db, user, company_id)[1])}


@router.post('', status_code=201)
async def upload_document(company_id: int, file: UploadFile = File(...), document_type: str = Form(...),
                          notes: str = Form(''), user=Depends(require_compliance_access), db: Session = Depends(get_db)):
    preliminary_access(db, user, company_id, write=True)
    if document_type not in CATEGORIES:
        raise HTTPException(400, 'Invalid corporate document category')
    db.rollback()
    name, content = await validated_pdf(file, notes)
    access(db, user, company_id, write=True)
    row = CorporateDocument(company_id=company_id, document_type=document_type,
                            original_file_name=name, notes=notes,
                            uploaded_by_user_id=user['timestation_id'], content=content)
    try:
        db.add(row)
        db.flush()
        result = metadata(row)
        record_audit(db, user, company_id, 'upload', new=result)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {'document': result}
