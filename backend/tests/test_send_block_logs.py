"""Real-DB test for GET /api/v1/campaigns/send-blocks — the single unified
place to answer "why didn't this send", built 2026-08-13 after repeatedly
having to grep server logs across the segment-cooldown, per-contact-cooldown,
recipient-cap, consent, and template gates separately to explain one blocked
message. Also confirms log_send_block() itself persists correctly and scopes
strictly to the calling advertiser (never leaks another advertiser's blocks)."""
import uuid

import pytest
from sqlalchemy import delete

from app.api.v1.campaigns import list_send_blocks
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.send_block_log import REASON_CONTACT_COOLDOWN, REASON_SEGMENT_COOLDOWN, SendBlockLog
from app.models.user import User
from app.services.send_block_log_service import log_send_block


async def _seed_user_and_contact():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x")
        db.add(user)
        await db.flush()
        contact = Contact(advertiser_id=user.id, name="Bloqueado", phone="+525500002222", source="landing")
        db.add(contact)
        await db.commit()
        return user.id, contact.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(SendBlockLog).where(SendBlockLog.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()


class TestSendBlockLogsEndpoint:
    @pytest.mark.asyncio
    async def test_lists_own_blocks_with_reason_and_contact_name(self):
        user_id, contact_id = await _seed_user_and_contact()
        other_user_id, _ = await _seed_user_and_contact()
        try:
            async with AsyncSessionLocal() as db:
                log_send_block(
                    db, user_id, REASON_CONTACT_COOLDOWN, contact_id=contact_id, detail="test",
                )
                log_send_block(db, other_user_id, REASON_SEGMENT_COOLDOWN)
                await db.commit()

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                out = await list_send_blocks(limit=50, db=db, current_user=user)

            assert len(out["items"]) == 1
            item = out["items"][0]
            assert item["reason"] == REASON_CONTACT_COOLDOWN
            assert item["contact_name"] == "Bloqueado"
            assert item["detail"] == "test"
        finally:
            await _cleanup([user_id, other_user_id])
