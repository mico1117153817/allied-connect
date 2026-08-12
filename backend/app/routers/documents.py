import hashlib
import json
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import get_db
from app.models.document import Document
from app.models.document_assignment import DocumentAssignment
from app.models.document_recipient_template import DocumentRecipientTemplate
from app.models.document_signature import DocumentSignature
from app.models.employee import Employee
from app.routers.auth import get_current_user, require_manager
from app.services.email import send_document_notification, send_document_void_notification

router = APIRouter(prefix="/api/documents", tags=["documents"])
STORAGE_DIR = Path(settings.STORAGE_DIR)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


class AcknowledgmentInput(BaseModel):
    acknowledged: bool = False


class TemplateInput(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    employee_ids: list[str] = Field(..., min_length=1)


def _get_assignment(db: Session, doc_id: int, employee_id: str) -> DocumentAssignment | None:
    return db.query(DocumentAssignment).filter(
        DocumentAssignment.document_id == doc_id,
        DocumentAssignment.employee_id == employee_id,
        DocumentAssignment.voided_at.is_(None),
    ).first()


def _serialize_document(db: Session, doc: Document, employee_id: str) -> dict:
    assignment = _get_assignment(db, doc.id, employee_id)
    signature = db.query(DocumentSignature).filter(
        DocumentSignature.document_id == doc.id,
        DocumentSignature.employee_id == employee_id,
    ).first()
    return {
        "id": doc.id,
        "title": doc.title,
        "file_type": doc.file_type,
        "version": doc.version,
        "requires_signature": doc.requires_signature,
        "viewed": bool(assignment and assignment.viewed_at),
        "viewed_at": assignment.viewed_at.isoformat() if assignment and assignment.viewed_at else None,
        "signed": signature is not None,
        "signed_at": signature.signed_at.isoformat() if signature and signature.signed_at else None,
        "created_at": doc.created_at.isoformat() if doc.created_at else None,
    }


def _parse_employee_ids(raw: str) -> list[str]:
    try:
        values = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "employee_ids must be a JSON array") from exc
    if not isinstance(values, list) or not values:
        raise HTTPException(400, "Select at least one employee")
    return list(dict.fromkeys(str(value) for value in values if value))


@router.get("")
async def list_documents(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    assignments = db.query(DocumentAssignment).filter(
        DocumentAssignment.employee_id == user["timestation_id"],
        DocumentAssignment.voided_at.is_(None),
    ).all()
    doc_ids = [row.document_id for row in assignments]
    docs = db.query(Document).filter(Document.id.in_(doc_ids), Document.is_active.is_(True)).order_by(Document.created_at.desc(), Document.id.desc()).all() if doc_ids else []
    return {"documents": [_serialize_document(db, doc, user["timestation_id"]) for doc in docs]}


@router.get("/requirements")
async def document_requirements(user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    data = (await list_documents(user, db))["documents"]
    unviewed = [doc for doc in data if not doc["viewed"]]
    blocking = [doc for doc in data if doc["requires_signature"] and not doc["signed"]]
    return {
        "has_blocking_documents": bool(blocking),
        "blocking_documents": blocking,
        "has_new_documents": bool(unviewed),
        "new_documents": unviewed,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def upload_document(
    title: str = Form(...), file: UploadFile = File(...), version: str = Form("1.0"),
    requires_signature: bool = Form(True), employee_ids: str = Form(...),
    user: dict = Depends(require_manager), db: Session = Depends(get_db),
):
    recipient_ids = _parse_employee_ids(employee_ids)
    recipients = db.query(Employee).filter(Employee.timestation_id.in_(recipient_ids), Employee.is_active.is_(True)).all()
    found_ids = {employee.timestation_id for employee in recipients}
    missing = [employee_id for employee_id in recipient_ids if employee_id not in found_ids]
    if missing:
        raise HTTPException(400, f"Unknown or inactive employees: {', '.join(missing)}")

    filename = file.filename or "document"
    if not filename.lower().endswith(".pdf") or (file.content_type and file.content_type.lower() != "application/pdf"):
        raise HTTPException(400, "Documents must be uploaded as PDF files")
    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(400, "The uploaded file is not a valid PDF")
    ext = "pdf"
    doc = Document(title=title, file_path="", file_type=ext, version=version,
                   requires_signature=requires_signature, created_by=user["timestation_id"])
    db.add(doc)
    db.flush()
    safe_name = filename.replace("/", "_").replace("\\", "_")
    file_path = STORAGE_DIR / f"{doc.id}_{safe_name}"
    try:
        file_path.write_bytes(content)
        doc.file_path = str(file_path)
        for employee in recipients:
            db.add(DocumentAssignment(document_id=doc.id, employee_id=employee.timestation_id,
                                      assigned_by=user["timestation_id"]))
        db.commit()
        db.refresh(doc)
    except Exception:
        db.rollback()
        if file_path.exists():
            file_path.unlink()
        raise

    for employee in recipients:
        if employee.email:
            try:
                await send_document_notification(to_email=employee.email, employee_name=employee.name,
                                                 document_title=doc.title, requires_signature=doc.requires_signature)
            except Exception as exc:
                print(f"[documents] notification failed for {employee.email}: {exc}")
    return {"id": doc.id, "title": doc.title, "version": doc.version, "file_type": doc.file_type,
            "status": "sent", "recipient_count": len(recipients)}


@router.post("/templates", status_code=status.HTTP_201_CREATED)
async def create_template(payload: TemplateInput, user: dict = Depends(require_manager), db: Session = Depends(get_db)):
    employee_ids = list(dict.fromkeys(payload.employee_ids))
    found = db.query(Employee).filter(Employee.timestation_id.in_(employee_ids), Employee.is_active.is_(True)).count()
    if found != len(employee_ids):
        raise HTTPException(400, "One or more selected employees are invalid or inactive")
    template = DocumentRecipientTemplate(name=payload.name.strip(), employee_ids_json=json.dumps(employee_ids),
                                         created_by=user["timestation_id"])
    db.add(template)
    db.commit()
    db.refresh(template)
    return {"id": template.id, "name": template.name, "employee_ids": employee_ids}


@router.get("/templates")
async def list_templates(user: dict = Depends(require_manager), db: Session = Depends(get_db)):
    templates = db.query(DocumentRecipientTemplate).filter(
        DocumentRecipientTemplate.created_by == user["timestation_id"]
    ).order_by(DocumentRecipientTemplate.name).all()
    employee_map = {employee.timestation_id: employee.name for employee in db.query(Employee).all()}
    result = []
    for template in templates:
        ids = json.loads(template.employee_ids_json or "[]")
        result.append({"id": template.id, "name": template.name, "employee_ids": ids,
                       "employee_names": [employee_map.get(employee_id, employee_id) for employee_id in ids]})
    return {"templates": result}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: int, user: dict = Depends(require_manager), db: Session = Depends(get_db)):
    template = db.query(DocumentRecipientTemplate).filter(
        DocumentRecipientTemplate.id == template_id,
        DocumentRecipientTemplate.created_by == user["timestation_id"],
    ).first()
    if not template:
        raise HTTPException(404, "Template not found")
    db.delete(template)
    db.commit()
    return {"status": "deleted"}


@router.get("/all/list")
async def list_all_documents(user: dict = Depends(require_manager), db: Session = Depends(get_db)):
    docs = db.query(Document).order_by(Document.created_at.desc(), Document.id.desc()).all()
    result = []
    for doc in docs:
        recipient_count = db.query(DocumentAssignment).filter(DocumentAssignment.document_id == doc.id).count()
        active_count = db.query(DocumentAssignment).filter(DocumentAssignment.document_id == doc.id,
                                                            DocumentAssignment.voided_at.is_(None)).count()
        result.append({"id": doc.id, "title": doc.title, "file_type": doc.file_type, "version": doc.version,
                       "is_active": doc.is_active, "is_voided": not doc.is_active and active_count == 0,
                       "requires_signature": doc.requires_signature, "recipient_count": recipient_count,
                       "created_at": doc.created_at.isoformat() if doc.created_at else None})
    return {"documents": result}


def _authorized_document(db: Session, doc_id: int, user: dict) -> tuple[Document, DocumentAssignment]:
    doc = db.query(Document).filter(Document.id == doc_id, Document.is_active.is_(True)).first()
    assignment = _get_assignment(db, doc_id, user["timestation_id"])
    if not doc or not assignment:
        raise HTTPException(404, "Document not available")
    return doc, assignment


@router.post("/{doc_id}/review")
async def review_document(doc_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    _, assignment = _authorized_document(db, doc_id, user)
    if not assignment.viewed_at:
        assignment.viewed_at = datetime.utcnow()
        db.commit()
    return {"status": "reviewed", "document_id": doc_id}


@router.get("/{doc_id}/history-download")
async def download_document_history(doc_id: int, user: dict = Depends(require_manager), db: Session = Depends(get_db)):
    """Managers retain read-only access to the PDF in document history, including voided records."""
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(404, "File not found on disk")
    return FileResponse(path=str(file_path), filename=f"{doc.title}.pdf", media_type="application/pdf",
                        content_disposition_type="inline")


@router.get("/{doc_id}/download")
async def download_document(doc_id: int, user: dict = Depends(get_current_user), db: Session = Depends(get_db)):
    doc, _ = _authorized_document(db, doc_id, user)
    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(404, "File not found on disk")
    filename = file_path.name.split("_", 1)[-1] if "_" in file_path.name else file_path.name
    return FileResponse(path=str(file_path), filename=filename, media_type="application/pdf",
                        content_disposition_type="inline")


@router.post("/{doc_id}/sign")
async def sign_document(
    doc_id: int,
    payload: AcknowledgmentInput,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc, assignment = _authorized_document(db, doc_id, user)
    if not doc.requires_signature:
        raise HTTPException(400, "This document does not require a signature")
    if not assignment.viewed_at:
        raise HTTPException(400, "You must review the document before signing")
    if not payload.acknowledged:
        raise HTTPException(400, "You must acknowledge that you have read the document before signing")
    existing = db.query(DocumentSignature).filter(DocumentSignature.document_id == doc_id,
                                                   DocumentSignature.employee_id == user["timestation_id"]).first()
    if existing:
        raise HTTPException(400, "Already signed")
    timestamp = datetime.utcnow().isoformat()
    db.add(DocumentSignature(document_id=doc_id, employee_id=user["timestation_id"],
                             signature_hash=hashlib.sha256(f"{user['timestation_id']}:{doc_id}:{timestamp}".encode()).hexdigest()))
    db.commit()
    return {"status": "signed", "document_id": doc_id}


@router.get("/{doc_id}/signatures")
async def get_signatures(doc_id: int, user: dict = Depends(require_manager), db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    assignments = db.query(DocumentAssignment).filter(DocumentAssignment.document_id == doc_id).all()
    signatures = db.query(DocumentSignature).filter(DocumentSignature.document_id == doc_id).all()
    employee_map = {employee.timestation_id: employee.name for employee in db.query(Employee).all()}
    signature_map = {signature.employee_id: signature for signature in signatures}
    signed, not_signed = [], []
    for assignment in assignments:
        item = {"employee_id": assignment.employee_id,
                "employee_name": employee_map.get(assignment.employee_id, "Unknown")}
        signature = signature_map.get(assignment.employee_id)
        if signature:
            item["signed_at"] = signature.signed_at.isoformat() if signature.signed_at else None
            signed.append(item)
        elif assignment.voided_at is None:
            not_signed.append(item)
    return {"document_title": doc.title, "signed": signed, "not_signed": not_signed,
            "total_signed": len(signed), "total_not_signed": len(not_signed)}


@router.put("/{doc_id}/void")
async def void_document(doc_id: int, user: dict = Depends(require_manager), db: Session = Depends(get_db)):
    doc = db.query(Document).filter(Document.id == doc_id, Document.is_active.is_(True)).first()
    if not doc:
        raise HTTPException(404, "Active document not found")
    assignments = db.query(DocumentAssignment).filter(DocumentAssignment.document_id == doc_id,
                                                        DocumentAssignment.voided_at.is_(None)).all()
    employees = {employee.timestation_id: employee for employee in db.query(Employee).filter(
        Employee.timestation_id.in_([assignment.employee_id for assignment in assignments])).all()}
    now = datetime.utcnow()
    doc.is_active = False
    for assignment in assignments:
        assignment.voided_at = now
        assignment.voided_by = user["timestation_id"]
    db.commit()
    for assignment in assignments:
        employee = employees.get(assignment.employee_id)
        if employee and employee.email:
            try:
                await send_document_void_notification(to_email=employee.email, employee_name=employee.name,
                                                       document_title=doc.title)
            except Exception as exc:
                print(f"[documents] void notification failed for {employee.email}: {exc}")
    return {"id": doc.id, "status": "voided", "recipient_count": len(assignments)}


@router.put("/{doc_id}/deactivate")
async def deactivate_document(doc_id: int, user: dict = Depends(require_manager), db: Session = Depends(get_db)):
    return await void_document(doc_id, user, db)
