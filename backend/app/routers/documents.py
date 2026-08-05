import os
import hashlib
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.models.database import get_db
from app.models.document import Document
from app.models.document_signature import DocumentSignature
from app.models.employee import Employee
from app.routers.auth import get_current_user, require_manager
from app.config import settings

router = APIRouter(prefix="/api/documents", tags=["documents"])

STORAGE_DIR = Path(settings.STORAGE_DIR)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)


# ── List active documents (all employees) ──────────────────────

@router.get("")
async def list_documents(
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    docs = db.query(Document).filter(Document.is_active == True).all()
    result = []
    for doc in docs:
        # Check if current user has signed
        signed = (
            db.query(DocumentSignature)
            .filter(
                DocumentSignature.document_id == doc.id,
                DocumentSignature.employee_id == user["timestation_id"],
            )
            .first()
        )
        result.append(
            {
                "id": doc.id,
                "title": doc.title,
                "file_type": doc.file_type,
                "version": doc.version,
                "requires_signature": doc.requires_signature,
                "signed": signed is not None,
                "signed_at": signed.signed_at.isoformat() if signed else None,
                "created_at": doc.created_at.isoformat() if doc.created_at else None,
            }
        )
    return {"documents": result}


# ── Upload document (manager only) ─────────────────────────────

@router.post("")
async def upload_document(
    title: str = Form(...),
    file: UploadFile = File(...),
    version: str = Form("1.0"),
    requires_signature: bool = Form(True),
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    # Determine file type
    filename = file.filename or "document"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "unknown"

    # Create DB record first to get ID
    doc = Document(
        title=title,
        file_path="",  # will update after save
        file_type=ext,
        version=version,
        requires_signature=requires_signature,
        created_by=user["timestation_id"],
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # Save file
    safe_name = filename.replace("/", "_").replace("\\", "_")
    file_path = STORAGE_DIR / f"{doc.id}_{safe_name}"
    content = await file.read()
    file_path.write_bytes(content)

    doc.file_path = str(file_path)
    db.commit()

    return {
        "id": doc.id,
        "title": doc.title,
        "version": doc.version,
        "file_type": doc.file_type,
        "status": "uploaded",
    }


# ── Download document ──────────────────────────────────────────

@router.get("/{doc_id}/download")
async def download_document(
    doc_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if not doc.is_active:
        raise HTTPException(404, "Document not available")

    file_path = Path(doc.file_path)
    if not file_path.exists():
        raise HTTPException(404, "File not found on disk")

    filename = file_path.name.split("_", 1)[-1] if "_" in file_path.name else file_path.name
    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )


# ── Sign document (employee) ───────────────────────────────────

@router.post("/{doc_id}/sign")
async def sign_document(
    doc_id: int,
    user: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    if not doc.requires_signature:
        raise HTTPException(400, "This document does not require a signature")

    # Check if already signed
    existing = (
        db.query(DocumentSignature)
        .filter(
            DocumentSignature.document_id == doc_id,
            DocumentSignature.employee_id == user["timestation_id"],
        )
        .first()
    )
    if existing:
        raise HTTPException(400, "Already signed")

    # Create signature record
    sig = DocumentSignature(
        document_id=doc_id,
        employee_id=user["timestation_id"],
        signature_hash=hashlib.sha256(
            f"{user['timestation_id']}:{doc_id}:{__import__('datetime').datetime.now().isoformat()}".encode()
        ).hexdigest(),
    )
    db.add(sig)
    db.commit()

    return {"status": "signed", "document_id": doc_id}


# ── View signatures (manager only) ─────────────────────────────

@router.get("/{doc_id}/signatures")
async def get_signatures(
    doc_id: int,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")

    signatures = (
        db.query(DocumentSignature)
        .filter(DocumentSignature.document_id == doc_id)
        .all()
    )
    # Get all employees to cross-reference
    all_employees = db.query(Employee).all()
    emp_map = {e.timestation_id: e.name for e in all_employees}

    signed = [
        {
            "employee_id": s.employee_id,
            "employee_name": emp_map.get(s.employee_id, "Unknown"),
            "signed_at": s.signed_at.isoformat() if s.signed_at else None,
        }
        for s in signatures
    ]

    # Also list who hasn't signed
    signed_ids = {s.employee_id for s in signatures}
    not_signed = [
        {"employee_id": e.timestation_id, "employee_name": e.name}
        for e in all_employees
        if e.timestation_id not in signed_ids and e.is_active
    ]

    return {
        "document_title": doc.title,
        "signed": signed,
        "not_signed": not_signed,
        "total_signed": len(signed),
        "total_not_signed": len(not_signed),
    }


# ── Deactivate old version when new one uploaded ────────────────

class DeactivateInput(BaseModel):
    document_id: int


@router.put("/{doc_id}/deactivate")
async def deactivate_document(
    doc_id: int,
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    doc = db.query(Document).filter(Document.id == doc_id).first()
    if not doc:
        raise HTTPException(404, "Document not found")
    doc.is_active = False
    db.commit()
    return {"id": doc.id, "is_active": False}


# ── List all documents including inactive (manager only) ───────

@router.get("/all/list")
async def list_all_documents(
    user: dict = Depends(require_manager),
    db: Session = Depends(get_db),
):
    docs = db.query(Document).order_by(Document.created_at.desc()).all()
    return {
        "documents": [
            {
                "id": d.id,
                "title": d.title,
                "file_type": d.file_type,
                "version": d.version,
                "is_active": d.is_active,
                "requires_signature": d.requires_signature,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    }
