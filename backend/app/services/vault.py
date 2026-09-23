import hashlib
import os
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.models.task import VaultAudit, VaultEntry, VaultSession, VaultUnlock

ALLOWED_VAULT_EMPLOYEE_IDS = frozenset({"local_f2a5804ba2e5", "local_262a0ca4abea"})
_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)


def vault_employee_allowed(employee_id):
    return employee_id in ALLOWED_VAULT_EMPLOYEE_IDS


def _utcnow():
    return datetime.now(timezone.utc)


class VaultService:
    def __init__(self, db, lock_minutes=15):
        self.db = db
        self.lock_minutes = lock_minutes
        raw = os.environ.get("PASSWORD_VAULT_KEY", "")
        try:
            import base64
            self.key = base64.urlsafe_b64decode(raw)
        except Exception as exc:
            raise RuntimeError("PASSWORD_VAULT_KEY must be URL-safe base64") from exc
        if len(self.key) != 32:
            raise RuntimeError("PASSWORD_VAULT_KEY must decode to exactly 32 bytes")

    def _audit(self, employee_id, action, entry_id=None, success=True):
        self.db.add(VaultAudit(employee_id=employee_id, action=action, entry_id=entry_id, success=success))

    def configure_unlock(self, employee_id, password):
        if not vault_employee_allowed(employee_id) or len(password) < 12:
            raise PermissionError("Vault access denied")
        if self.db.get(VaultUnlock, employee_id):
            self._audit(employee_id, "unlock_configure_rejected", success=False)
            self.db.commit()
            raise FileExistsError("Vault password is already configured")
        row = VaultUnlock(employee_id=employee_id)
        row.password_hash = _hasher.hash(password)
        self.db.add(row); self._audit(employee_id, "unlock_configured"); self.db.commit()

    def unlock(self, employee_id, password):
        if not vault_employee_allowed(employee_id):
            raise PermissionError("Vault access denied")
        row = self.db.get(VaultUnlock, employee_id)
        try:
            valid = bool(row) and _hasher.verify(row.password_hash, password)
        except VerifyMismatchError:
            valid = False
        if not valid:
            self._audit(employee_id, "unlock_failed", success=False); self.db.commit(); return None
        token = secrets.token_urlsafe(32)
        self.db.add(VaultSession(token_hash=self._hash_token(token), employee_id=employee_id, expires_at=_utcnow() + timedelta(minutes=self.lock_minutes)))
        self._audit(employee_id, "unlocked"); self.db.commit(); return token

    @staticmethod
    def _hash_token(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def _session(self, token, employee_id):
        row = self.db.get(VaultSession, self._hash_token(token or ""))
        now = _utcnow()
        expires = row.expires_at.replace(tzinfo=timezone.utc) if row and row.expires_at.tzinfo is None else (row.expires_at if row else now)
        if not row or row.employee_id != employee_id or row.revoked_at or expires <= now or not vault_employee_allowed(employee_id):
            raise PermissionError("Vault is locked")
        row.expires_at = now + timedelta(minutes=self.lock_minutes)
        return row

    def _encrypt(self, value):
        if value is None: return None
        nonce = os.urandom(12)
        return nonce + AESGCM(self.key).encrypt(nonce, value.encode(), b"allied-password-vault-v1")

    def _decrypt(self, value):
        if value is None: return None
        return AESGCM(self.key).decrypt(value[:12], value[12:], b"allied-password-vault-v1").decode()

    def create_entry(self, token, employee_id, name, username, password, url, notes, company_id=1):
        self._session(token, employee_id)
        from app.models.compliance_company import ComplianceCompany
        if not self.db.get(ComplianceCompany, company_id):
            raise LookupError("Company not found")
        row = VaultEntry(company_id=company_id, name=name, username_ciphertext=self._encrypt(username), secret_ciphertext=self._encrypt(password), url_ciphertext=self._encrypt(url), notes_ciphertext=self._encrypt(notes), created_by=employee_id)
        self.db.add(row); self.db.flush(); self._audit(employee_id, "entry_created", row.id); self.db.commit(); self.db.refresh(row); return row

    def list_entries(self, token, employee_id, company_id):
        self._session(token, employee_id)
        query = self.db.query(VaultEntry).filter(VaultEntry.archived_at.is_(None))
        query = query.filter(VaultEntry.company_id == company_id)
        rows = query.order_by(VaultEntry.name).all()
        self.db.commit()
        return [{"id": r.id, "company_id": r.company_id, "name": r.name, "username": self._decrypt(r.username_ciphertext), "url": self._decrypt(r.url_ciphertext), "notes": self._decrypt(r.notes_ciphertext), "password_masked": "••••••••"} for r in rows]

    def reveal(self, token, employee_id, entry_id, company_id=None):
        self._session(token, employee_id)
        query = self.db.query(VaultEntry).filter(VaultEntry.id == entry_id, VaultEntry.archived_at.is_(None))
        if company_id is not None:
            query = query.filter(VaultEntry.company_id == company_id)
        row = query.first()
        if not row or row.archived_at: raise LookupError("Entry not found")
        self._audit(employee_id, "secret_revealed", row.id); self.db.commit()
        return {"password": self._decrypt(row.secret_ciphertext)}

    def lock_now(self, token, employee_id):
        row = self._session(token, employee_id); row.revoked_at = _utcnow(); self._audit(employee_id, "locked"); self.db.commit()
