from datetime import date, datetime, timezone
import base64
import hashlib
import json
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.config import settings
from app.models.compliance_attachment import ComplianceAttachment
from app.models.compliance_audit import ComplianceAudit, snapshot, audit_diff, audit_event
from app.models.compliance_company import ComplianceCompany, CompanyPermission, CompanyLogo
from app.models.database import get_db
from app.models.setting import Setting
from app.models.state_compliance import StateCompliance
from app.models.employee import Employee
from app.routers.auth import require_compliance_access, require_manager

router = APIRouter(prefix="/api/compliance", tags=["compliance"])

STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "Florida", "Georgia",
    "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland",
    "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
    "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
    "District of Columbia",
]
EDITABLE_REQUIREMENTS = {"Required", "Not Required"}
ITEM_TYPES = {"license", "certificate_of_authority", "bond", "annual_report", "filing_receipt"}
ITEM_LABELS = {"license": "License", "certificate_of_authority": "Certificate of Authority", "bond": "Bond", "annual_report": "Annual Report", "filing_receipt": "Filing Receipt"}
EDITABLE_STATUSES = {"Active", "Pending", "Not Held"}
CONFIDENCE_LEVELS = {"Verified", "High", "Medium", "Low", "Unverified"}
ANNUAL_REPORT_REQUIREMENTS = {"Not Required", "Annual", "Bi-Annual"}
SOURCE_PATH = "Licensing/Allied_Licensing_Matrix.xlsx"
SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "state_compliance_seed.json"
DATE_FIELDS = {
    "license_issue_date", "license_expiration", "license_renewal_due",
    "coa_issue_date", "bond_expiration",
}
JSON_LIST_FIELDS = {"source_urls": "source_urls_json", "document_paths": "document_paths_json"}


class ComplianceInput(BaseModel):
    jurisdiction: str | None = None
    collection_license_requirement: str = "Not Required"
    license_status: str = "Not Held"
    license_number: str | None = None
    license_issue_date: date | None = None
    license_expiration: date | None = None
    license_renewal_due: date | None = None
    coa_requirement: str = "Not Required"
    coa_status: str = "Not Held"
    coa_number: str | None = None
    coa_issue_date: date | None = None
    certificate_of_authority: bool = False
    bond_requirement: str = "Not Required"
    bond_status: str = "Not Held"
    bond_number: str | None = None
    bond_requirement_amount: float | None = Field(None, ge=0)
    renewal_structure: str | None = None
    general_requirement_notes: str | None = None
    bond_amount: float | None = Field(None, ge=0)
    bond_expiration: date | None = None
    annual_report_requirement: str = "Not Required"
    annual_report_due_date: date | None = None
    annual_report_renewal_date: date | None = None
    regulator: str | None = None
    state_portal_url: str | None = None
    portal_username: str | None = None
    portal_password: str | None = None
    clear_portal_password: bool = False
    notes: str | None = None
    source_urls: list[str] = []
    document_paths: list[str] = []
    data_confidence: str = "Unverified"


def _seed_row(row: StateCompliance, seed: dict) -> None:
    for field, value in seed.items():
        if field in {"state", "source_urls", "document_paths"}:
            continue
        if field in DATE_FIELDS and value:
            value = date.fromisoformat(value)
        if hasattr(row, field):
            setattr(row, field, value)
    for source_field, model_field in JSON_LIST_FIELDS.items():
        setattr(row, model_field, json.dumps(seed.get(source_field, [])))
    if not row.state_portal_url and seed.get("source_urls"):
        row.state_portal_url = seed["source_urls"][0]


def _row_is_empty(row: StateCompliance) -> bool:
    meaningful_fields = (
        "license_number", "license_issue_date", "license_expiration", "license_renewal_due",
        "coa_number", "coa_issue_date", "bond_number", "bond_amount", "bond_expiration",
        "regulator", "notes", "source_urls_json", "document_paths_json",
    )
    if any(getattr(row, field, None) not in (None, "", "[]") for field in meaningful_fields):
        return False
    return (
        row.license_status in (None, "Not Held")
        and row.coa_status in (None, "Unknown")
        and not row.certificate_of_authority
        and row.bond_status in (None, "Unknown")
    )


def _merge_matrix_seed(row: StateCompliance, seed: dict) -> bool:
    """Merge workbook-backed seed fields into existing rows without removing manual values."""
    if SOURCE_PATH not in seed.get("document_paths", []):
        return False
    changed = False
    for field, value in seed.items():
        if field in {"state", "source_urls", "document_paths"} or value in (None, "", []):
            continue
        if field in DATE_FIELDS:
            value = date.fromisoformat(value)
        current = getattr(row, field, None)
        if current in (None, "") or (field.endswith("_requirement") and current == "Unknown") or (field in {"coa_status", "bond_status"} and current == "Unknown"):
            setattr(row, field, value)
            changed = True
    if row.coa_status in {"Active", "Perpetual"} and not row.certificate_of_authority:
        row.certificate_of_authority = True
        changed = True
    if not row.state_portal_url and seed.get("source_urls"):
        row.state_portal_url = seed["source_urls"][0]
        changed = True
    paths = _loads_list(row.document_paths_json)
    if SOURCE_PATH not in paths:
        paths.append(SOURCE_PATH)
        row.document_paths_json = json.dumps(paths)
        changed = True
    return changed


def _default_company(db):
    company = db.get(ComplianceCompany, 1)
    if company is None:
        company = ComplianceCompany(id=1, legal_name="Allied Alliance Group Inc.")
        db.add(company)
        db.flush()
        for employee in db.query(Employee).filter_by(role="admin"):
            db.add(CompanyPermission(employee_id=employee.timestation_id, company_id=1, can_edit=True))
        db.flush()
    return company


def _ensure_states(db: Session, company_id: int = 1, commit: bool = True):
    company = _default_company(db) if company_id == 1 else db.get(ComplianceCompany, company_id)
    rows = {row.state: row for row in db.query(StateCompliance).filter_by(company_id=company_id).all()}
    seeds = {}
    if company_id == 1 and not company.legacy_preserved and SEED_PATH.exists():
        seeds = {item["state"]: item for item in json.loads(SEED_PATH.read_text(encoding="utf-8"))}

    changed = False
    for state in STATES:
        row = rows.get(state)
        if row is None:
            row = StateCompliance(state=state, company_id=company_id)
            if company_id != 1:
                row.license_status = row.coa_status = row.bond_status = 'Not Held'
            db.add(row)
            rows[state] = row
            if state in seeds:
                _seed_row(row, seeds[state])
            changed = True
        elif row.updated_by is None and state in seeds and _row_is_empty(row):
            _seed_row(row, seeds[state])
            changed = True
        elif row.updated_by is None and state in seeds and _merge_matrix_seed(row, seeds[state]):
            changed = True
        if not company.legacy_preserved and not row.state_portal_url_migrated:
            legacy_urls = _loads_list(row.source_urls_json)
            if not row.state_portal_url and legacy_urls:
                row.state_portal_url = legacy_urls[0]
            row.state_portal_url_migrated = True
            changed = True
    if changed and commit:
        db.commit()


def _attachment_summary(db: Session, state: str, company_id: int = 1, include_archived: bool = False) -> dict[str, list[dict]]:
    result = {item_type: [] for item_type in ITEM_TYPES}
    query = db.query(ComplianceAttachment).filter(ComplianceAttachment.state == state, ComplianceAttachment.company_id == company_id)
    if not include_archived:
        query = query.filter(ComplianceAttachment.archived_at.is_(None))
    rows = query.order_by(ComplianceAttachment.created_at.desc(), ComplianceAttachment.id.desc()).all()
    for row in rows:
        result[row.item_type].append({
            "id": row.id, "item_type": row.item_type, "label": ITEM_LABELS[row.item_type],
            "filename": row.filename, "content_type": row.content_type,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "archived_at": row.archived_at.isoformat() if row.archived_at else None,
            "is_archived": row.archived_at is not None,
            "view_url": f"/api/compliance/{state}/attachments/{row.id}/view?company_id={company_id}" + ('&include_archived=true' if row.archived_at else ''),
        })
    return result


def _loads_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _credential_key(db: Session) -> bytes:
    if settings.COMPLIANCE_CREDENTIAL_KEY:
        raw = settings.COMPLIANCE_CREDENTIAL_KEY
    else:
        row = db.query(Setting).filter(Setting.key == "compliance_credential_key").first()
        if not row:
            # The caller owns the transaction: never commit a partially edited row here.
            # ON CONFLICT serializes concurrent first-key creation on SQLite/PostgreSQL.
            db.execute(text("INSERT INTO settings (key, value, description) VALUES (:key, :value, :description) ON CONFLICT (key) DO NOTHING"), {
                "key": "compliance_credential_key", "value": Fernet.generate_key().decode("ascii"),
                "description": "Persistent encryption key for compliance portal credentials",
            })
            raw = db.execute(text("SELECT value FROM settings WHERE key=:key"), {"key": "compliance_credential_key"}).scalar_one()
        else:
            raw = row.value
    try:
        Fernet(raw.encode("ascii"))
        return raw.encode("ascii")
    except (ValueError, TypeError) as exc:
        raise HTTPException(500, "Compliance credential encryption key is invalid") from exc


def _fernet(db: Session) -> Fernet:
    return Fernet(_credential_key(db))


def _encrypt_password(db: Session, value: str) -> str:
    return _fernet(db).encrypt(value.encode("utf-8")).decode("ascii")


def _legacy_fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def _decrypt_password(db: Session, value: str) -> str:
    try:
        return _fernet(db).decrypt(value.encode("ascii")).decode("utf-8")
    except InvalidToken:
        try:
            plaintext = _legacy_fernet().decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise HTTPException(500, "Stored portal password cannot be decrypted; contact the system administrator") from exc
        return plaintext


def _expiration_issues(row: StateCompliance) -> list[str]:
    today = date.today()
    issues = []
    if row.collection_license_requirement == "Required" and row.license_status == "Expired":
        issues.append("License status is Expired")
    if row.collection_license_requirement == "Required" and row.license_expiration and row.license_expiration < today:
        issues.append(f"License expired on {row.license_expiration.isoformat()}")
    if row.collection_license_requirement == "Required" and row.license_renewal_due and row.license_renewal_due < today:
        issues.append(f"License renewal was due on {row.license_renewal_due.isoformat()}")
    if row.bond_requirement == "Required" and row.bond_status == "Expired":
        issues.append("Bond status is Expired")
    if row.bond_requirement == "Required" and row.bond_expiration and row.bond_expiration < today:
        issues.append(f"Bond expired on {row.bond_expiration.isoformat()}")
    if row.annual_report_requirement != "Not Required" and row.annual_report_renewal_date and row.annual_report_renewal_date < today:
        issues.append(f"Annual report renewal was due on {row.annual_report_renewal_date.isoformat()}")
    return issues


def _review_issues(row: StateCompliance, overall_status: str) -> list[str]:
    issues = _expiration_issues(row)
    if overall_status != "Needs Review":
        return issues
    for label, requirement in (
        ("License", row.collection_license_requirement),
        ("Certificate of Authority", row.coa_requirement),
        ("Bond", row.bond_requirement),
    ):
        if requirement in {"Unknown", "Conditional", "Local Only"}:
            issues.append(f"{label} requirement is {requirement}")
    return list(dict.fromkeys(issues))


def _requirement_satisfied(requirement: str, status: str, active_statuses: set[str]) -> bool | None:
    if requirement == "Not Required":
        return True
    if requirement in {"Unknown", "Conditional", "Local Only"}:
        return None
    return status in active_statuses


def _overall(row: StateCompliance) -> tuple[str, str]:
    if _expiration_issues(row):
        return "Needs Review", "yellow"
    checks = [
        _requirement_satisfied(row.collection_license_requirement, row.license_status, {"Active", "Perpetual"}),
        _requirement_satisfied(row.coa_requirement, row.coa_status, {"Active", "Perpetual"}),
        _requirement_satisfied(row.bond_requirement, row.bond_status, {"Active"}),
    ]
    if any(value is False for value in checks):
        return "Not Authorized", "red"
    if all(value is True for value in checks):
        return "Active", "green"
    return "Needs Review", "yellow"


def _serialize(db: Session, row: StateCompliance) -> dict:
    overall_status, indicator = _overall(row)
    return {
        "company_id": row.company_id,
        "bond_requirement_amount": float(row.bond_requirement_amount) if row.bond_requirement_amount is not None else None,
        "renewal_structure": row.renewal_structure,
        "general_requirement_notes": row.general_requirement_notes,
        "state": row.state,
        "jurisdiction": row.jurisdiction or row.state,
        "collection_license_requirement": row.collection_license_requirement,
        "license_status": row.license_status,
        "license_number": row.license_number,
        "license_issue_date": row.license_issue_date.isoformat() if row.license_issue_date else None,
        "license_expiration": row.license_expiration.isoformat() if row.license_expiration else None,
        "license_renewal_due": row.license_renewal_due.isoformat() if row.license_renewal_due else None,
        "coa_requirement": row.coa_requirement,
        "coa_status": row.coa_status,
        "coa_number": row.coa_number,
        "coa_issue_date": row.coa_issue_date.isoformat() if row.coa_issue_date else None,
        "certificate_of_authority": row.certificate_of_authority,
        "bond_requirement": row.bond_requirement,
        "bond_status": row.bond_status,
        "bond_number": row.bond_number,
        "bond_amount": float(row.bond_amount) if row.bond_amount is not None else None,
        "bond_expiration": row.bond_expiration.isoformat() if row.bond_expiration else None,
        "annual_report_requirement": row.annual_report_requirement,
        "annual_report_due_date": row.annual_report_due_date.isoformat() if row.annual_report_due_date else None,
        "annual_report_renewal_date": row.annual_report_renewal_date.isoformat() if row.annual_report_renewal_date else None,
        "annual_report_completed_at": f"{row.annual_report_completed_at.isoformat()}Z" if row.annual_report_completed_at else None,
        "annual_report_completed_by": row.annual_report_completed_by,
        "annual_report_completed_by_name": row.annual_report_completed_by_name,
        "annual_report_completion_removed_at": f"{row.annual_report_completion_removed_at.isoformat()}Z" if row.annual_report_completion_removed_at else None,
        "annual_report_completion_removed_by": row.annual_report_completion_removed_by,
        "annual_report_completion_removed_by_name": row.annual_report_completion_removed_by_name,
        "regulator": row.regulator,
        "state_portal_url": row.state_portal_url,
        "portal_username": row.portal_username,
        "has_portal_password": bool(row.portal_password_encrypted),
        "issues": _review_issues(row, overall_status),
        "attachments": _attachment_summary(db, row.state, row.company_id),
        "notes": row.notes,
        "source_urls": _loads_list(row.source_urls_json),
        "document_paths": _loads_list(row.document_paths_json),
        "data_confidence": row.data_confidence,
        "overall_status": overall_status,
        "indicator": indicator,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


REQUIREMENT_COPY_FIELDS = (
    "jurisdiction", "collection_license_requirement", "coa_requirement", "bond_requirement",
    "bond_requirement_amount", "annual_report_requirement", "renewal_structure",
    "regulator", "state_portal_url", "general_requirement_notes",
)


class CompanyInput(BaseModel):
    legal_name: str = Field(min_length=1, max_length=300)
    dba_name: str | None = None
    entity_type: str | None = None
    ein: str | None = None
    formation_state: str | None = None
    formation_date: date | None = None
    business_address: str | None = None
    mailing_address: str | None = None
    phone: str | None = None
    email: str | None = None
    website: str | None = None
    registered_agent: str | None = None
    registered_agent_address: str | None = None
    notes: str | None = None
    is_active: bool = True
    copy_from_company_id: int | None = None

    @field_validator('legal_name', mode='before')
    @classmethod
    def validate_legal_name(cls, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Legal company name is required')
        return value.strip()


class CompanyUpdate(CompanyInput):
    legal_name: str | None = Field(None, min_length=1, max_length=300)


def _company_json(company):
    return {c.name: getattr(company, c.name) for c in company.__table__.columns if c.name != 'legacy_preserved'}


def _rights(db, user, company_id):
    if user.get("role") == "super_admin":
        return True, True
    if user.get("role") != "admin":
        return False, False
    permission = db.query(CompanyPermission).filter_by(employee_id=user.get("timestation_id"), company_id=company_id).first()
    if permission:
        return True, permission.can_edit
    return False, False


def _company_access(db, user, company_id, write=False):
    company = _default_company(db) if company_id == 1 else db.get(ComplianceCompany, company_id)
    if company is None:
        raise HTTPException(404, 'Company not found')
    visible, editable = _rights(db, user, company_id)
    if not visible or (write and (not editable or not company.is_active)):
        raise HTTPException(403, 'Company access denied or company archived')
    return company


def _summary(db, company_id):
    rows = db.query(StateCompliance).filter_by(company_id=company_id).all()
    result = dict.fromkeys(('total', 'active', 'needs_review', 'not_authorized',
                           'licenses_expiring_30', 'licenses_expiring_60', 'licenses_expiring_90',
                           'bonds_expiring_soon', 'annual_reports_due_soon', 'open_issues', 'expiring_soon'), 0)
    def soon(value, days=90):
        return value is not None and 0 <= (value - date.today()).days <= days
    for row in rows:
        status, _ = _overall(row)
        result['total'] += 1
        result[status.lower().replace(' ', '_')] += 1
        result['open_issues'] += bool(_review_issues(row, status))
        license_soon = row.collection_license_requirement == 'Required' and soon(row.license_expiration)
        bond_soon = row.bond_requirement == 'Required' and soon(row.bond_expiration)
        report_soon = row.annual_report_requirement != 'Not Required' and soon(row.annual_report_renewal_date or row.annual_report_due_date)
        for days in (30, 60, 90):
            result[f'licenses_expiring_{days}'] += row.collection_license_requirement == 'Required' and soon(row.license_expiration, days)
        result['bonds_expiring_soon'] += bond_soon
        result['annual_reports_due_soon'] += report_soon
        result['expiring_soon'] += bool(license_soon or bond_soon or report_soon)
    return result


def _company_result(db, user, company):
    return {**_company_json(company), 'summary': _summary(db, company.id), 'can_edit': bool(company.is_active and _rights(db, user, company.id)[1]),
            'can_manage': bool(_rights(db, user, company.id)[1])}


@router.get('/companies')
async def list_companies(user: dict = Depends(require_compliance_access), db: Session = Depends(get_db)):
    _ensure_states(db)
    return {'companies': [_company_result(db, user, c) for c in db.query(ComplianceCompany).order_by(ComplianceCompany.id) if _rights(db, user, c.id)[0]],
            'can_manage': True, 'is_super_admin': user.get('role') == 'super_admin'}


@router.post('/companies', status_code=201)
async def create_company(payload: CompanyInput, user: dict = Depends(require_compliance_access), db: Session = Depends(get_db)):
    _ensure_states(db)
    if payload.copy_from_company_id is not None:
        _company_access(db, user, payload.copy_from_company_id)
    company = ComplianceCompany(**payload.model_dump(exclude={'copy_from_company_id'}))
    db.add(company)
    db.flush()
    db.add(CompanyPermission(employee_id=user.get("timestation_id"), company_id=company.id, can_edit=True))
    _ensure_states(db, company.id, commit=False)
    db.flush()
    if payload.copy_from_company_id is not None:
        _company_access(db, user, payload.copy_from_company_id)
        source = {r.state: r for r in db.query(StateCompliance).filter_by(company_id=payload.copy_from_company_id)}
        for row in db.query(StateCompliance).filter_by(company_id=company.id):
            if row.state in source:
                for field in REQUIREMENT_COPY_FIELDS:
                    setattr(row, field, getattr(source[row.state], field))
    db.commit()
    return _company_json(company)


@router.post("/companies/{company_id}/logo")
async def upload_company_logo(company_id: int, file: UploadFile = File(...), user: dict = Depends(require_compliance_access), db: Session = Depends(get_db)):
    from io import BytesIO
    from PIL import Image, UnidentifiedImageError
    company = _company_access(db, user, company_id, write=True)
    content = await file.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(400, "Logo exceeds 5 MiB")
    try:
        image = Image.open(BytesIO(content))
        if image.format not in {"PNG", "JPEG"} or image.width * image.height > 16_000_000:
            raise ValueError("Invalid image format or dimensions")
        mime = "image/png" if image.format == "PNG" else "image/jpeg"
        image.load()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError) as exc:
        raise HTTPException(400, "Logo must be a valid PNG or JPEG") from exc
    logo = db.get(CompanyLogo, company_id)
    old_hash = hashlib.sha256(logo.content).hexdigest() if logo else None
    if logo is None:
        logo = CompanyLogo(company_id=company_id)
        db.add(logo)
    logo.content, logo.content_type = content, mime
    new_hash = hashlib.sha256(content).hexdigest()
    company.logo_path = f"/api/compliance/companies/{company_id}/logo?v={new_hash}"
    if old_hash != new_hash:
        audit_event(db, user, company_id, None, "logo.upload", old_hash, new_hash)
    db.commit()
    return _company_result(db, user, company)


@router.get("/companies/{company_id}/logo")
async def view_company_logo(company_id: int, user: dict = Depends(require_compliance_access), db: Session = Depends(get_db)):
    _company_access(db, user, company_id)
    logo = db.get(CompanyLogo, company_id)
    if logo is None:
        raise HTTPException(404, "Logo not found")
    return Response(content=logo.content, media_type=logo.content_type,
                    headers={"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"})


@router.get("/companies/{company_id}/audit")
async def company_audit(company_id: int, state: str | None = None, user: dict = Depends(require_compliance_access), db: Session = Depends(get_db)):
    _company_access(db, user, company_id)
    query = db.query(ComplianceAudit).filter_by(company_id=company_id)
    if state is not None:
        query = query.filter_by(state=state)
    return {"events": [{key: getattr(e, key) for key in ("id", "user_name", "state", "field", "old_value", "new_value", "created_at")}
                       for e in query.order_by(ComplianceAudit.id.desc())]}


@router.get("/companies/{company_id}")
async def get_company(company_id: int, user: dict = Depends(require_compliance_access), db: Session = Depends(get_db)):
    return _company_result(db, user, _company_access(db, user, company_id))


@router.put("/companies/{company_id}")
async def update_company(company_id: int, payload: CompanyUpdate, user: dict = Depends(require_compliance_access), db: Session = Depends(get_db)):
    company = _company_access(db, user, company_id)
    if not _rights(db, user, company_id)[1]:
        raise HTTPException(403, "Company management denied")
    before = snapshot(company)
    for field, value in payload.model_dump(exclude_unset=True, exclude={"copy_from_company_id"}).items():
        setattr(company, field, value)
    audit_diff(db, user, company_id, None, before, company)
    db.commit()
    return _company_result(db, user, company)


@router.get("")
async def list_compliance(company_id: int = 1, user: dict = Depends(require_compliance_access), db: Session = Depends(get_db)):
    company = _company_access(db, user, company_id)
    _ensure_states(db, company_id)
    rows = db.query(StateCompliance).filter_by(company_id=company_id).order_by(StateCompliance.state).all()
    return {"states": [_serialize(db, row) for row in rows], "company": _company_json(company), "can_edit": bool(company.is_active and _rights(db, user, company_id)[1])}


@router.get("/{state}/attachments")
async def list_compliance_attachments(
    state: str,
    item_type: str | None = None,
    include_archived: bool = False,
    user: dict = Depends(require_compliance_access),
    db: Session = Depends(get_db),
    company_id: int = 1,
):
    _company_access(db, user, company_id)
    if state not in STATES:
        raise HTTPException(404, "State not found")
    if item_type is not None and item_type not in ITEM_TYPES:
        raise HTTPException(400, "Invalid compliance attachment item type")
    summary = _attachment_summary(db, state, company_id, include_archived)
    return {"attachments": [item for key, items in summary.items() if item_type is None or key == item_type for item in items]}


@router.post("/{state}/attachments", status_code=201)
async def upload_compliance_attachment(
    state: str,
    item_type: str = Form(""),
    file: UploadFile = File(...),
    user: dict = Depends(require_compliance_access),
    db: Session = Depends(get_db),
    company_id: int = 1,
):
    _company_access(db, user, company_id, write=True)
    if state not in STATES or item_type not in ITEM_TYPES:
        raise HTTPException(400, "Invalid state or compliance attachment item type")
    filename = file.filename or "attachment.pdf"
    if not filename.lower().endswith(".pdf") or file.content_type not in (None, "application/pdf"):
        raise HTTPException(400, "Compliance attachments must be PDF files")
    content = await file.read()
    if not content.startswith(b"%PDF"):
        raise HTTPException(400, "The uploaded file is not a valid PDF")
    attachment = ComplianceAttachment(company_id=company_id, state=state, item_type=item_type, filename=filename.replace("/", "_").replace("\\", "_"), content_type="application/pdf", content=content, uploaded_by=user.get("timestation_id"))
    db.add(attachment)
    db.flush()
    audit_event(db, user, company_id, state, "attachment.upload", None, f"{attachment.id}: {attachment.filename}")
    db.commit()
    db.refresh(attachment)
    return {"attachment": _attachment_summary(db, state, company_id)[item_type][0]}


@router.get("/{state}/attachments/{attachment_id}/view")
async def view_compliance_attachment(
    state: str,
    attachment_id: int,
    response: Response,
    include_archived: bool = False,
    user: dict = Depends(require_compliance_access),
    db: Session = Depends(get_db),
    company_id: int = 1,
):
    _company_access(db, user, company_id)
    row = db.query(ComplianceAttachment).filter(ComplianceAttachment.id == attachment_id, ComplianceAttachment.state == state, ComplianceAttachment.company_id == company_id).first()
    if not row or (row.archived_at is not None and not include_archived):
        raise HTTPException(404, "Compliance attachment not found")
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    return Response(content=row.content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{row.filename}"', "Cache-Control": "no-store, no-cache, must-revalidate, private", "Pragma": "no-cache"})


@router.delete("/{state}/attachments/{attachment_id}", status_code=204)
async def delete_compliance_attachment(
    state: str,
    attachment_id: int,
    user: dict = Depends(require_compliance_access),
    db: Session = Depends(get_db),
    company_id: int = 1,
):
    _company_access(db, user, company_id, write=True)
    row = db.query(ComplianceAttachment).filter(ComplianceAttachment.id == attachment_id, ComplianceAttachment.state == state, ComplianceAttachment.company_id == company_id).first()
    if not row:
        raise HTTPException(404, "Compliance attachment not found")
    if row.archived_at is None:
        row.archived_at = datetime.now(timezone.utc).replace(tzinfo=None)
        row.archived_by = user.get("timestation_id")
        audit_event(db, user, company_id, state, "attachment.archive", row.filename, f"{row.id}: archived")
    db.commit()
    return Response(status_code=204)


@router.get("/{state}/portal-credentials")
async def get_portal_credentials(
    state: str,
    response: Response,
    include_archived: bool = False,
    user: dict = Depends(require_compliance_access),
    db: Session = Depends(get_db),
    company_id: int = 1,
):
    _company_access(db, user, company_id)
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    if state not in STATES:
        raise HTTPException(404, "State not found")
    _ensure_states(db, company_id)
    row = db.query(StateCompliance).filter_by(state=state, company_id=company_id).one()
    return {
        "username": row.portal_username,
        "password": _decrypt_password(db, row.portal_password_encrypted) if row.portal_password_encrypted else None,
    }


@router.put("/{state}")
async def update_compliance(
    state: str,
    payload: ComplianceInput,
    user: dict = Depends(require_compliance_access),
    db: Session = Depends(get_db),
    company_id: int = 1,
):
    _company_access(db, user, company_id, write=True)
    if state not in STATES:
        raise HTTPException(404, "State not found")
    if payload.collection_license_requirement not in EDITABLE_REQUIREMENTS or payload.coa_requirement not in EDITABLE_REQUIREMENTS or payload.bond_requirement not in EDITABLE_REQUIREMENTS:
        raise HTTPException(400, "Requirement must be Required or Not Required")
    if payload.license_status not in EDITABLE_STATUSES:
        raise HTTPException(400, "License status must be Active, Pending, or Not Held")
    if payload.coa_status not in EDITABLE_STATUSES:
        raise HTTPException(400, "COA status must be Active, Pending, or Not Held")
    if payload.bond_status not in EDITABLE_STATUSES:
        raise HTTPException(400, "Bond status must be Active, Pending, or Not Held")
    if payload.data_confidence not in CONFIDENCE_LEVELS:
        raise HTTPException(400, "Invalid confidence value")
    if payload.annual_report_requirement not in ANNUAL_REPORT_REQUIREMENTS:
        raise HTTPException(400, "Annual report requirement must be Not Required, Annual, or Bi-Annual")
    _ensure_states(db, company_id)
    row = db.query(StateCompliance).filter_by(state=state, company_id=company_id).one()
    before = snapshot(row)
    values = payload.model_dump(exclude={"source_urls", "document_paths", "portal_password"})
    for field, value in values.items():
        setattr(row, field, value)
    row.state_portal_url_migrated = True
    if payload.clear_portal_password:
        row.portal_password_encrypted = None
    elif payload.portal_password:
        row.portal_password_encrypted = _encrypt_password(db, payload.portal_password)
    for prefix, requirement_field in (("license", "collection_license_requirement"), ("coa", "coa_requirement"), ("bond", "bond_requirement")):
        if getattr(payload, requirement_field) == "Not Required":
            if prefix == "license":
                row.license_status = "Not Held"
                row.license_number = None
                row.license_issue_date = None
                row.license_expiration = None
                row.license_renewal_due = None
            elif prefix == "coa":
                row.coa_status = "Not Held"
                row.coa_number = None
                row.coa_issue_date = None
                row.certificate_of_authority = False
            else:
                row.bond_status = "Not Held"
                row.bond_number = None
                row.bond_amount = None
                row.bond_expiration = None
    row.source_urls_json = json.dumps(payload.source_urls)
    row.document_paths_json = json.dumps(payload.document_paths)
    row.certificate_of_authority = row.coa_requirement == "Required" and payload.coa_status == "Active"
    if payload.annual_report_requirement == "Not Required":
        row.annual_report_due_date = None
        row.annual_report_renewal_date = None
    row.updated_by = user.get("timestation_id")
    audit_diff(db, user, company_id, state, before, row)
    db.commit()
    db.refresh(row)
    return _serialize(db, row)


@router.post("/{state}/annual-report/complete")
async def complete_annual_report(
    state: str,
    user: dict = Depends(require_compliance_access),
    db: Session = Depends(get_db),
    company_id: int = 1,
):
    _company_access(db, user, company_id, write=True)
    if state not in STATES:
        raise HTTPException(404, "State not found")
    _ensure_states(db, company_id)
    row = db.query(StateCompliance).filter_by(state=state, company_id=company_id).one()
    before = snapshot(row)
    row.annual_report_completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    row.annual_report_completed_by = user.get("timestation_id")
    row.annual_report_completed_by_name = user.get("name")
    row.annual_report_completion_removed_at = None
    row.annual_report_completion_removed_by = None
    row.annual_report_completion_removed_by_name = None
    row.updated_by = user.get("timestation_id")
    audit_diff(db, user, company_id, state, before, row)
    db.commit()
    db.refresh(row)
    return _serialize(db, row)


@router.post("/{state}/annual-report/remove-completion")
async def remove_annual_report_completion(
    state: str,
    user: dict = Depends(require_compliance_access),
    db: Session = Depends(get_db),
    company_id: int = 1,
):
    _company_access(db, user, company_id, write=True)
    if state not in STATES:
        raise HTTPException(404, "State not found")
    _ensure_states(db, company_id)
    row = db.query(StateCompliance).filter_by(state=state, company_id=company_id).one()
    before = snapshot(row)
    row.annual_report_completed_at = None
    row.annual_report_completed_by = None
    row.annual_report_completed_by_name = None
    row.annual_report_completion_removed_at = datetime.now(timezone.utc).replace(tzinfo=None)
    row.annual_report_completion_removed_by = user.get("timestation_id")
    row.annual_report_completion_removed_by_name = user.get("name")
    row.updated_by = user.get("timestation_id")
    audit_diff(db, user, company_id, state, before, row)
    db.commit()
    db.refresh(row)
    return _serialize(db, row)
