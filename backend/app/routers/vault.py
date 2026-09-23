from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import get_db
from app.routers.auth import get_current_user
from app.services.vault import VaultService, vault_employee_allowed
from app.models.task import VaultEntry, VaultUnlock
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


def _deny_cache(response: Response):
    response.headers["Cache-Control"] = "no-store, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"


def _allowed(user=Depends(get_current_user)):
    if not vault_employee_allowed(user.get("timestation_id")):
        raise HTTPException(404, "Not found")
    return user


def _service(db):
    try: return VaultService(db, settings.PASSWORD_VAULT_LOCK_MINUTES)
    except RuntimeError as exc: raise HTTPException(503, str(exc))


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


@router.post("/entries", status_code=201)
def create_entry(payload: EntryInput, response: Response, x_vault_token: str = Header(""), user=Depends(_allowed), db: Session = Depends(get_db)):
    _company_access(db, user, payload.company_id, write=True)
    try: row = _service(db).create_entry(x_vault_token, user["timestation_id"], **payload.model_dump())
    except PermissionError as exc: raise HTTPException(423, str(exc))
    _deny_cache(response); return {"id": row.id, "name": row.name}


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
