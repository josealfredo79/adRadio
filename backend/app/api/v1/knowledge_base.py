"""
Knowledge Base router — /api/v1/knowledge-base
"""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User
from app.workers.tasks import process_knowledge_base_file

router = APIRouter(prefix="/knowledge-base", tags=["knowledge-base"])

ALLOWED_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "text/plain": "txt",
    "image/jpeg": "image",
    "image/png": "image",
    "audio/mpeg": "audio",
    "audio/mp4": "audio",
    "audio/wav": "audio",
}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB


@router.get("")
async def list_files(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(KnowledgeBase)
        .where(
            KnowledgeBase.advertiser_id == current_user.id,
            KnowledgeBase.is_active == True,  # noqa: E712
        )
        .order_by(KnowledgeBase.created_at.desc())
    )
    files = result.scalars().all()
    return [
        {
            "id": str(f.id),
            "filename": f.filename,
            "file_type": f.file_type,
            "version": f.version,
            "processing_status": f.processing_status,
            "created_at": f.created_at,
        }
        for f in files
    ]


@router.post("/upload", status_code=status.HTTP_202_ACCEPTED)
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Validate MIME type (not just extension)
    if file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Tipo de archivo no soportado: {file.content_type}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="El archivo supera el límite de 50MB")

    file_type = ALLOWED_MIME_TYPES[file.content_type]

    # Save record (processing happens in background)
    kb = KnowledgeBase(
        advertiser_id=current_user.id,
        filename=file.filename or "archivo",
        file_type=file_type,
    )
    db.add(kb)
    await db.commit()
    await db.refresh(kb)

    # Dispatch processing to Celery (text extraction + embeddings)
    process_knowledge_base_file.delay(str(kb.id), content, file_type)

    return {"message": "Archivo recibido. Se procesará en segundo plano.", "id": str(kb.id)}


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(KnowledgeBase).where(
            KnowledgeBase.id == file_id,
            KnowledgeBase.advertiser_id == current_user.id,
        )
    )
    kb = result.scalar_one_or_none()
    if not kb:
        raise HTTPException(status_code=404, detail="Archivo no encontrado")

    await db.delete(kb)
    await db.commit()


@router.post("/test")
async def test_bot(
    body: dict,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.services.rag_service import answer_with_rag

    query = body.get("query", "")
    if not query:
        raise HTTPException(status_code=400, detail="Proporciona una query")

    answer = await answer_with_rag(
        advertiser_id=str(current_user.id),
        query=query,
        conversation_history=[],
        db=db,
    )
    return {"answer": answer}
