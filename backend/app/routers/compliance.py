from datetime import date
import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.state_compliance import StateCompliance
from app.routers.auth import require_compliance_access

router = APIRouter(prefix="/api/compliance", tags=["compliance"])

STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "Florida", "Georgia",
    "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland",
    "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
    "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
    "District of Columbia",
]
REQUIREMENTS = {"Required", "Not Required", "Local Only", "Conditional", "Unknown"}
LICENSE_STATUSES = {"Active", "Expired", "Pending", "Not Held", "Want to Get", "Not Required", "Perpetual", "Terminated", "Unknown"}
COA_STATUSES = {"Active", "Pending", "Not Held", "Not Required", "Perpetual", "Revoked", "Terminated", "Unknown"}
BOND_STATUSES = {"Active", "Expired", "Pending", "Not Held", "Not Required", "Unknown"}
CONFIDENCE_LEVELS = {"Verified", "High", "Medium", "Low", "Unverified"}
SOURCE_PATH = "Licensing/Allied_Licensing_Matrix.xlsx"
SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "state_compliance_seed.json"
DATE_FIELDS = {
    "license_issue_date", "license_expiration", "license_renewal_due",
    "coa_issue_date", "bond_expiration",
}
JSON_LIST_FIELDS = {"source_urls": "source_urls_json", "document_paths": "document_paths_json"}


class ComplianceInput(BaseModel):
    jurisdiction: str | None = None
    collection_license_requirement: str = "Unknown"
    license_status: str = "Not Held"
    license_number: str | None = None
    license_issue_date: date | None = None
    license_expiration: date | None = None
    license_renewal_due: date | None = None
    coa_requirement: str = "Unknown"
    coa_status: str = "Unknown"
    coa_number: str | None = None
    coa_issue_date: date | None = None
    certificate_of_authority: bool = False
    bond_requirement: str = "Unknown"
    bond_status: str = "Unknown"
    bond_number: str | None = None
    bond_amount: float | None = Field(None, ge=0)
    bond_expiration: date | None = None
    regulator: str | None = None
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
        if current in (None, "") or (field.endswith("_requirement") and current == "Unknown") or (field in {"coa_status", "bond_status"} and current == "Unknown") or (field == "data_confidence" and current == "Unverified"):
            setattr(row, field, value)
            changed = True
    if row.coa_status in {"Active", "Perpetual"} and not row.certificate_of_authority:
        row.certificate_of_authority = True
        changed = True
    paths = _loads_list(row.document_paths_json)
    if SOURCE_PATH not in paths:
        paths.append(SOURCE_PATH)
        row.document_paths_json = json.dumps(paths)
        changed = True
    return changed


def _ensure_states(db: Session):
    rows = {row.state: row for row in db.query(StateCompliance).all()}
    seeds = {}
    if SEED_PATH.exists():
        seeds = {item["state"]: item for item in json.loads(SEED_PATH.read_text(encoding="utf-8"))}

    changed = False
    for state in STATES:
        row = rows.get(state)
        if row is None:
            row = StateCompliance(state=state)
            db.add(row)
            rows[state] = row
            if state in seeds:
                _seed_row(row, seeds[state])
            changed = True
        elif row.updated_by is None and row.data_confidence == "Unverified" and state in seeds and _row_is_empty(row):
            _seed_row(row, seeds[state])
            changed = True
        elif row.updated_by is None and state in seeds and _merge_matrix_seed(row, seeds[state]):
            changed = True
    if changed:
        db.commit()


def _loads_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except (TypeError, ValueError):
        return []


def _requirement_satisfied(requirement: str, status: str, active_statuses: set[str]) -> bool | None:
    if requirement == "Not Required":
        return True
    if requirement in {"Unknown", "Conditional", "Local Only"}:
        return None
    return status in active_statuses


def _overall(row: StateCompliance) -> tuple[str, str]:
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


def _serialize(row: StateCompliance) -> dict:
    overall_status, indicator = _overall(row)
    return {
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
        "regulator": row.regulator,
        "notes": row.notes,
        "source_urls": _loads_list(row.source_urls_json),
        "document_paths": _loads_list(row.document_paths_json),
        "data_confidence": row.data_confidence,
        "overall_status": overall_status if row.data_confidence != "Unverified" else "Unknown",
        "indicator": indicator if row.data_confidence != "Unverified" else "gray",
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("")
async def list_compliance(user: dict = Depends(require_compliance_access), db: Session = Depends(get_db)):
    _ensure_states(db)
    rows = db.query(StateCompliance).order_by(StateCompliance.state).all()
    return {"states": [_serialize(row) for row in rows]}


@router.put("/{state}")
async def update_compliance(
    state: str,
    payload: ComplianceInput,
    user: dict = Depends(require_compliance_access),
    db: Session = Depends(get_db),
):
    if state not in STATES:
        raise HTTPException(404, "State not found")
    if payload.collection_license_requirement not in REQUIREMENTS or payload.coa_requirement not in REQUIREMENTS or payload.bond_requirement not in REQUIREMENTS:
        raise HTTPException(400, "Invalid requirement value")
    if payload.license_status not in LICENSE_STATUSES:
        raise HTTPException(400, "Invalid license status")
    if payload.coa_status not in COA_STATUSES:
        raise HTTPException(400, "Invalid COA status")
    if payload.bond_status not in BOND_STATUSES:
        raise HTTPException(400, "Invalid bond status")
    if payload.data_confidence not in CONFIDENCE_LEVELS:
        raise HTTPException(400, "Invalid confidence value")
    _ensure_states(db)
    row = db.query(StateCompliance).filter(StateCompliance.state == state).first()
    values = payload.model_dump(exclude={"source_urls", "document_paths"})
    for field, value in values.items():
        setattr(row, field, value)
    row.source_urls_json = json.dumps(payload.source_urls)
    row.document_paths_json = json.dumps(payload.document_paths)
    row.certificate_of_authority = payload.coa_status in {"Active", "Perpetual"}
    row.updated_by = user.get("timestation_id")
    db.commit()
    db.refresh(row)
    return _serialize(row)
