"""Real-DB integration tests for knowledge_base.py — zero coverage existed
before this file. Covers list/upload/get-content/delete ownership scoping,
the RAG feature-plan gate (list_files has no gate, upload/test do), MIME
type whitelist, the 50MB size limit, and the is_active soft-delete filter.
Unlike admin/public_api/user_webhooks, this router returns plain dicts
(not Pydantic response models), so there's no str/UUID/datetime response
typing to break — checked, no bug found."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.api.v1.knowledge_base import delete_file, get_file_content, list_files, upload_file
from app.api.v1.knowledge_base import test_bot as ask_bot
from app.database import AsyncSessionLocal, engine
from app.models.knowledge_base import KnowledgeBase
from app.models.user import User


async def _seed_user(current_plan: str = "trial"):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(
            email=f"{uuid.uuid4()}@test.com", password_hash="x",
            current_plan=current_plan, subscription_status="active",
        )
        db.add(user)
        await db.commit()
        return user.id


async def _seed_file(advertiser_id, filename="doc.pdf", is_active=True, raw_text=None):
    async with AsyncSessionLocal() as db:
        kb = KnowledgeBase(advertiser_id=advertiser_id, filename=filename, file_type="pdf", is_active=is_active, raw_text=raw_text)
        db.add(kb)
        await db.commit()
        return kb.id


def _upload(content: bytes, content_type: str, filename: str = "doc.pdf"):
    f = MagicMock()
    f.content_type = content_type
    f.filename = filename
    f.read = AsyncMock(return_value=content)
    return f


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(KnowledgeBase).where(KnowledgeBase.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestListFiles:
    @pytest.mark.asyncio
    async def test_only_returns_own_active_files(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            await _seed_file(owner_id, filename="mio.pdf")
            await _seed_file(owner_id, filename="borrado.pdf", is_active=False)
            await _seed_file(other_id, filename="ajeno.pdf")

            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                files = await list_files(db=db, current_user=owner, page=1, page_size=20)
            assert [f["filename"] for f in files] == ["mio.pdf"]
        finally:
            await _cleanup([owner_id, other_id])

    @pytest.mark.asyncio
    async def test_pagination_limits_page_size(self):
        user_id = await _seed_user()
        try:
            for i in range(3):
                await _seed_file(user_id, filename=f"f{i}.pdf")

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                page1 = await list_files(db=db, current_user=user, page=1, page_size=2)
                page2 = await list_files(db=db, current_user=user, page=2, page_size=2)
            assert len(page1) == 2
            assert len(page2) == 1
        finally:
            await _cleanup([user_id])


class TestUploadFile:
    @pytest.mark.asyncio
    async def test_trial_plan_blocked_with_402(self):
        user_id = await _seed_user(current_plan="trial")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await upload_file(
                        request=MagicMock(headers={}), file=_upload(b"hola", "application/pdf"),
                        db=db, current_user=user, _=None, redis=None,
                    )
                assert exc_info.value.status_code == 402
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_rejects_unsupported_mime_type(self):
        user_id = await _seed_user(current_plan="growth")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await upload_file(
                        request=MagicMock(headers={}), file=_upload(b"hola", "application/zip"),
                        db=db, current_user=user, _=None, redis=None,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_rejects_file_over_50mb(self):
        user_id = await _seed_user(current_plan="growth")
        try:
            oversized = b"x" * (50 * 1024 * 1024 + 1)
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await upload_file(
                        request=MagicMock(headers={}), file=_upload(oversized, "application/pdf"),
                        db=db, current_user=user, _=None, redis=None,
                    )
                assert exc_info.value.status_code == 413
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_growth_plan_uploads_and_dispatches_processing(self):
        user_id = await _seed_user(current_plan="growth")
        try:
            with patch("app.api.v1.knowledge_base.process_knowledge_base_file") as mock_task:
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    result = await upload_file(
                        request=MagicMock(headers={}), file=_upload(b"contenido", "application/pdf", filename="folleto.pdf"),
                        db=db, current_user=user, _=None, redis=None,
                    )
                assert "id" in result
                mock_task.delay.assert_called_once_with(result["id"], b"contenido", "pdf")

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                files = await list_files(db=db, current_user=user, page=1, page_size=20)
            assert [f["filename"] for f in files] == ["folleto.pdf"]
        finally:
            await _cleanup([user_id])


class TestGetFileContent:
    @pytest.mark.asyncio
    async def test_returns_raw_text(self):
        user_id = await _seed_user()
        try:
            file_id = await _seed_file(user_id, raw_text="texto extraído")
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result = await get_file_content(file_id=file_id, db=db, current_user=user)
            assert result["raw_text"] == "texto extraído"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unknown_file_returns_404(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await get_file_content(file_id=uuid.uuid4(), db=db, current_user=user)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_cannot_read_another_advertisers_file(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            file_id = await _seed_file(owner_id)
            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc_info:
                    await get_file_content(file_id=file_id, db=db, current_user=other)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([owner_id, other_id])


class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_deletes_and_disappears_from_list(self):
        user_id = await _seed_user()
        try:
            file_id = await _seed_file(user_id)
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await delete_file(file_id=file_id, db=db, current_user=user)
                remaining = await list_files(db=db, current_user=user, page=1, page_size=20)
            assert remaining == []
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unknown_file_returns_404(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await delete_file(file_id=uuid.uuid4(), db=db, current_user=user)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_cannot_delete_another_advertisers_file(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            file_id = await _seed_file(owner_id)
            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc_info:
                    await delete_file(file_id=file_id, db=db, current_user=other)
                assert exc_info.value.status_code == 404

            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                remaining = await list_files(db=db, current_user=owner, page=1, page_size=20)
            assert len(remaining) == 1
        finally:
            await _cleanup([owner_id, other_id])


class TestTestBot:
    @pytest.mark.asyncio
    async def test_trial_plan_blocked_with_402(self):
        user_id = await _seed_user(current_plan="trial")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await ask_bot(body={"query": "hola"}, db=db, current_user=user)
                assert exc_info.value.status_code == 402
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_empty_query_returns_400(self):
        user_id = await _seed_user(current_plan="growth")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await ask_bot(body={"query": ""}, db=db, current_user=user)
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_returns_rag_answer(self):
        user_id = await _seed_user(current_plan="growth")
        try:
            with patch("app.services.rag_service.answer_with_rag", new=AsyncMock(return_value="Respuesta del bot")) as mock_rag:
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    result = await ask_bot(body={"query": "¿tienen envíos?"}, db=db, current_user=user)
                assert result == {"answer": "Respuesta del bot"}
                mock_rag.assert_called_once()
        finally:
            await _cleanup([user_id])
