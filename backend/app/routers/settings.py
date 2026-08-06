from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.routers.auth import require_manager
from app.services.settings_service import get_setting, set_setting, DEFAULTS

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingUpdate(BaseModel):
    key: str
    value: str


# Keys that managers are allowed to change
EDITABLE_KEYS = {"late_threshold_minutes", "early_leave_threshold_minutes", "portal_name"}


@router.get("")
async def get_settings(
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """Get all configurable portal settings."""
    result = []
    for key, meta in DEFAULTS.items():
        result.append({
            "key": key,
            "value": get_setting(db, key),
            "description": meta["description"],
        })
    return {"settings": result}


@router.put("")
async def update_setting(
    req: SettingUpdate,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    """Update a portal setting. Only keys in EDITABLE_KEYS are allowed."""
    if req.key not in EDITABLE_KEYS:
        raise HTTPException(403, f"Setting '{req.key}' is not editable")

    # Validate thresholds are non-negative integers
    if req.key in ("late_threshold_minutes", "early_leave_threshold_minutes"):
        try:
            val = int(req.value)
            if val < 0:
                raise ValueError
        except ValueError:
            raise HTTPException(400, f"{req.key} must be a non-negative integer")

    row = set_setting(db, req.key, req.value)
    return {"key": row.key, "value": row.value, "updated": True}
