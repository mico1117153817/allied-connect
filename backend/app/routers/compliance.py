from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.database import get_db
from app.models.state_compliance import StateCompliance
from app.routers.auth import require_super_admin

router = APIRouter(prefix="/api/compliance", tags=["compliance"])

STATES = [
    "Alabama", "Alaska", "Arizona", "Arkansas", "California", "Colorado", "Connecticut", "Delaware", "Florida", "Georgia",
    "Hawaii", "Idaho", "Illinois", "Indiana", "Iowa", "Kansas", "Kentucky", "Louisiana", "Maine", "Maryland",
    "Massachusetts", "Michigan", "Minnesota", "Mississippi", "Missouri", "Montana", "Nebraska", "Nevada", "New Hampshire", "New Jersey",
    "New Mexico", "New York", "North Carolina", "North Dakota", "Ohio", "Oklahoma", "Oregon", "Pennsylvania", "Rhode Island", "South Carolina",
    "South Dakota", "Tennessee", "Texas", "Utah", "Vermont", "Virginia", "Washington", "West Virginia", "Wisconsin", "Wyoming",
]
LICENSE_STATUSES = {"Active", "Expired", "Pending", "Not Held", "Want to Get"}
BOND_STATUSES = {"Active", "Expired"}


class ComplianceInput(BaseModel):
    certificate_of_authority: bool = False
    license_status: str = "Not Held"
    license_number: str | None = None
    license_expiration: date | None = None
    bond_status: str = "Expired"
    bond_amount: float | None = Field(None, ge=0)


def _ensure_states(db: Session):
    existing = {row.state for row in db.query(StateCompliance).all()}
    missing = [StateCompliance(state=state) for state in STATES if state not in existing]
    if missing:
        db.add_all(missing)
        db.commit()


def _serialize(row: StateCompliance) -> dict:
    return {
        "state": row.state,
        "certificate_of_authority": row.certificate_of_authority,
        "license_status": row.license_status,
        "license_number": row.license_number,
        "license_expiration": row.license_expiration.isoformat() if row.license_expiration else None,
        "bond_status": row.bond_status,
        "bond_amount": float(row.bond_amount) if row.bond_amount is not None else None,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("")
async def list_compliance(user: dict = Depends(require_super_admin), db: Session = Depends(get_db)):
    _ensure_states(db)
    rows = db.query(StateCompliance).order_by(StateCompliance.id).all()
    return {"states": [_serialize(row) for row in rows]}


@router.put("/{state}")
async def update_compliance(
    state: str,
    payload: ComplianceInput,
    user: dict = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    if state not in STATES:
        raise HTTPException(404, "State not found")
    if payload.license_status not in LICENSE_STATUSES:
        raise HTTPException(400, "Invalid license status")
    if payload.bond_status not in BOND_STATUSES:
        raise HTTPException(400, "Invalid bond status")
    _ensure_states(db)
    row = db.query(StateCompliance).filter(StateCompliance.state == state).first()
    for field, value in payload.model_dump().items():
        setattr(row, field, value)
    row.updated_by = user.get("timestation_id")
    db.commit()
    db.refresh(row)
    return _serialize(row)
