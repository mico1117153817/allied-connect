from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import get_db
from app.routers.auth import get_current_user
from app.services.vault import VaultService, vault_employee_allowed
from app.models.task import VaultAudit, VaultCategory, VaultEntry, VaultUnlock
from app.routers.compliance import _company_access

router = APIRouter(prefix="/api/password-vault", tags=["password-vault"])


class UnlockInput(BaseModel):
    password: str = Field(min_length=12, max_length=256)


class EntryInput(BaseModel):
    company_id: int
    name: str = Field(min_length=1, max_length=200)
    username: str | None = None
    password: str = Field(min_length=1, max_length=2000)
    url: str | None = None
    notes: str | None = None
    account_ref: str | None = None
    mfa_notes: str | None = None
    recovery_notes: str | None = None
    category_id: int | None = None


class EntryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=200)
    username: str | None = None
    password: str | None = Field(None, min_length=1, max_length=2000)
    url: str | None = None
    notes: str | None = None
    account_ref: str | None = None
    mfa_notes: str | None = None
    recovery_notes: str | None = None
    category_id: int | None = None


class CategoryInput(BaseModel):
    name: str = Field(min_length=1, max_length=100)


def _deny_cache(response: Response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


def _user_can_vault(user: dict) -> bool:
    return bool(user.get("password_vault_access"))


def _allowed(user=Depends(get_current_user)):
    if not _user_can_vault(user):
        raise HTTPException(404, "Not found")
    return user


def _service(db):
    try: return VaultService(db, settings.PASSWORD_VAULT_LOCK_MINUTES)
    except RuntimeError as exc: raise HTTPException(503, str(exc))


@router.get("/categories")
def categories(user=Depends(_allowed), db: Session = Depends(get_db)):
    return {"categories": [{"id": row.id, "name": row.name} for row in db.query(VaultCategory).filter_by(is_active=True).order_by(VaultCategory.name).all()]}


@router.post("/categories", status_code=201)
def create_category(payload: CategoryInput, user=Depends(_allowed), db: Session = Depends(get_db)):
    if db.query(VaultCategory).filter(VaultCategory.name == payload.name).first(): raise HTTPException(409, "Vault category already exists")
    row = VaultCategory(name=payload.name, created_by=user["timestation_id"]); db.add(row); db.commit(); db.refresh(row)
    return {"id": row.id, "name": row.name}


@router.put("/categories/{category_id}")
def update_category(category_id: int, payload: CategoryInput, user=Depends(_allowed), db: Session = Depends(get_db)):
    row = db.query(VaultCategory).filter_by(id=category_id, is_active=True).first()
    if not row: raise HTTPException(404, "Vault category not found")
    row.name = payload.name; db.commit(); return {"id": row.id, "name": row.name}


@router.delete("/categories/{category_id}", status_code=204)
def archive_category(category_id: int, user=Depends(_allowed), db: Session = Depends(get_db)):
    row = db.query(VaultCategory).filter_by(id=category_id, is_active=True).first()
    if not row: raise HTTPException(404, "Vault category not found")
    row.is_active = False; db.commit()


@router.get("/status")
def status(response: Response, user=Depends(_allowed), db: Session = Depends(get_db)):
    _deny_cache(response)
    return {"configured": db.get(VaultUnlock, user["timestation_id"]) is not None, "lock_minutes": settings.PASSWORD_VAULT_LOCK_MINUTES}


@router.post("/configure", status_code=204)
def configure(payload: UnlockInput, response: Response, user=Depends(_allowed), db: Session = Depends(get_db)):
    try:
        _service(db).configure_unlock(user["timestation_id"], payload.password)
    except FileExistsError as exc:
        raise HTTPException(409, str(exc))
    _deny_cache(response)


@router.post("/unlock")
def unlock(payload: UnlockInput, response: Response, user=Depends(_allowed), db: Session = Depends(get_db)):
    token = _service(db).unlock(user["timestation_id"], payload.password)
    if not token: raise HTTPException(401, "Invalid vault password")
    _deny_cache(response); return {"vault_token": token, "expires_in_minutes": settings.PASSWORD_VAULT_LOCK_MINUTES}


@router.get("/entries")
def entries(response: Response, company_id: int, x_vault_token: str = Header(""), user=Depends(_allowed), db: Session = Depends(get_db)):
    _company_access(db, user, company_id)
    try: result = _service(db).list_entries(x_vault_token, user["timestation_id"], company_id)
    except PermissionError as exc: raise HTTPException(423, str(exc))
    _deny_cache(response); return {"entries": result}


@router.get("/audit")
def audit_log(response: Response, company_id: int, x_vault_token: str = Header(""), user=Depends(_allowed), db: Session = Depends(get_db)):
    _company_access(db, user, company_id)
    service = _service(db)
    try:
        service._session(x_vault_token, user["timestation_id"])
    except PermissionError as exc:
        raise HTTPException(423, str(exc))
    entry_ids = [entry_id for (entry_id,) in db.query(VaultEntry.id).filter(VaultEntry.company_id == company_id).all()]
    query = db.query(VaultAudit)
    if entry_ids:
        query = query.filter((VaultAudit.entry_id.in_(entry_ids)) | ((VaultAudit.entry_id.is_(None)) & (VaultAudit.employee_id == user["timestation_id"])))
    else:
        query = query.filter(VaultAudit.entry_id.is_(None), VaultAudit.employee_id == user["timestation_id"])
    rows = query.order_by(VaultAudit.created_at.desc()).limit(500).all()
    db.commit()
    _deny_cache(response)
    return {"events": [{"id": row.id, "employee_id": row.employee_id, "entry_id": row.entry_id, "action": row.action, "success": row.success, "created_at": row.created_at} for row in rows]}


@router.post("/entries", status_code=201)
def create_entry(payload: EntryInput, response: Response, x_vault_token: str = Header(""), user=Depends(_allowed), db: Session = Depends(get_db)):
    _company_access(db, user, payload.company_id, write=True)
    try: row = _service(db).create_entry(x_vault_token, user["timestation_id"], **payload.model_dump())
    except PermissionError as exc: raise HTTPException(423, str(exc))
    except LookupError as exc: raise HTTPException(404, str(exc))
    _deny_cache(response); return {"id": row.id, "name": row.name}


def _entry_scope(db, user, entry_id, write=False):
    row = db.query(VaultEntry).filter_by(id=entry_id, archived_at=None).first()
    if not row: raise HTTPException(404, "Entry not found")
    _company_access(db, user, row.company_id, write=write)
    return row


@router.get("/entries/{entry_id}")
def entry_detail(entry_id: int, response: Response, x_vault_token: str = Header(""), user=Depends(_allowed), db: Session = Depends(get_db)):
    row = _entry_scope(db, user, entry_id)
    try: result = _service(db).get_entry(x_vault_token, user["timestation_id"], entry_id, row.company_id)
    except PermissionError as exc: raise HTTPException(423, str(exc))
    _deny_cache(response); return result


@router.put("/entries/{entry_id}")
def update_entry(entry_id: int, payload: EntryUpdate, response: Response, x_vault_token: str = Header(""), user=Depends(_allowed), db: Session = Depends(get_db)):
    row = _entry_scope(db, user, entry_id, write=True)
    try: result = _service(db).update_entry(x_vault_token, user["timestation_id"], entry_id, row.company_id, **payload.model_dump(exclude_unset=True))
    except PermissionError as exc: raise HTTPException(423, str(exc))
    except LookupError as exc: raise HTTPException(404, str(exc))
    _deny_cache(response); return result


@router.delete("/entries/{entry_id}", status_code=204)
def archive_entry(entry_id: int, response: Response, x_vault_token: str = Header(""), user=Depends(_allowed), db: Session = Depends(get_db)):
    row = _entry_scope(db, user, entry_id, write=True)
    try: _service(db).archive_entry(x_vault_token, user["timestation_id"], entry_id, row.company_id)
    except PermissionError as exc: raise HTTPException(423, str(exc))
    _deny_cache(response)


@router.post("/entries/{entry_id}/copy")
def copy_entry(entry_id: int, response: Response, x_vault_token: str = Header(""), user=Depends(_allowed), db: Session = Depends(get_db)):
    row = _entry_scope(db, user, entry_id)
    try: result = _service(db).copy_secret(x_vault_token, user["timestation_id"], entry_id, row.company_id)
    except PermissionError as exc: raise HTTPException(423, str(exc))
    _deny_cache(response); return result


@router.post("/entries/{entry_id}/reveal")
def reveal(entry_id: int, response: Response, x_vault_token: str = Header(""), user=Depends(_allowed), db: Session = Depends(get_db)):
    entry = db.query(VaultEntry).filter_by(id=entry_id, archived_at=None).first()
    if not entry:
        raise HTTPException(404, "Entry not found")
    _company_access(db, user, entry.company_id)
    try: result = _service(db).reveal(x_vault_token, user["timestation_id"], entry_id, entry.company_id)
    except PermissionError as exc: raise HTTPException(423, str(exc))
    except LookupError as exc: raise HTTPException(404, str(exc))
    _deny_cache(response); return result


@router.post("/lock", status_code=204)
def lock(response: Response, x_vault_token: str = Header(""), user=Depends(_allowed), db: Session = Depends(get_db)):
    try: _service(db).lock_now(x_vault_token, user["timestation_id"])
    except PermissionError as exc: raise HTTPException(423, str(exc))
    _deny_cache(response)
