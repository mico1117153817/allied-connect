from sqlalchemy.orm import Session
from app.models.setting import Setting

DEFAULTS = {
    "late_threshold_minutes": {
        "value": "1",
        "description": "Minutes after scheduled start time before an employee is flagged as late",
    },
    "portal_name": {
        "value": "Allied Connect",
        "description": "Portal display name shown in the header and login page",
    },
}


def get_setting(db: Session, key: str, default: str | None = None) -> str | None:
    """Get a setting value, falling back to DEFAULTS then the provided default."""
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        return row.value
    if key in DEFAULTS:
        return DEFAULTS[key]["value"]
    return default


def set_setting(db: Session, key: str, value: str) -> Setting:
    """Create or update a setting."""
    row = db.query(Setting).filter(Setting.key == key).first()
    if row:
        row.value = value
    else:
        row = Setting(
            key=key,
            value=value,
            description=DEFAULTS.get(key, {}).get("description", ""),
        )
        db.add(row)
    db.commit()
    db.refresh(row)
    return row


def init_defaults(db: Session):
    """Seed default settings into the DB if they don't exist."""
    for key, meta in DEFAULTS.items():
        row = db.query(Setting).filter(Setting.key == key).first()
        if not row:
            db.add(Setting(
                key=key,
                value=meta["value"],
                description=meta["description"],
            ))
    db.commit()
