"""Antes de enviar una campaña: a cuántos les llega gratis por web y a cuántos
por WhatsApp (campaign_reach.py, GET /campaigns/{id}/reach), y el envío
"solo por web" (POST /campaigns/{id}/resume con web_only), que no manda nada
por WhatsApp ni gasta saldo. El push real nunca se toca."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1.campaigns import ResumeBody, campaign_reach_preview, resume_campaign
from app.database import AsyncSessionLocal
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.user import User
from app.services.campaign_reach import META_MARKETING_USD_MX, USD_TO_MXN, campaign_reach
from tests.test_web_push import _add_subs, _cleanup, _keys, _seed  # noqa: F401 — _keys es fixture autouse


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/campaigns/x/resume",
                    "headers": [], "client": ("test", 1), "query_string": b""})


async def _campaign(user_id, mode: str = "regular", messages_remaining: int = 5):
    async with AsyncSessionLocal() as db:
        camp = Campaign(advertiser_id=user_id, name="2x1 en cortes", type="promo",
                        message_text="2x1 este viernes", ab_test={"campaign_mode": mode})
        db.add(camp)
        user = await db.get(User, user_id)
        user.messages_remaining = messages_remaining
        await db.commit()
        return camp.id


class TestCampaignReach:
    @pytest.mark.asyncio
    async def test_splits_web_and_whatsapp_with_meta_cost(self):
        user_id, (with_push, _, _) = await _seed(3)
        try:
            await _add_subs(user_id, with_push, 2)  # dos navegadores = un cliente
            camp_id = await _campaign(user_id)
            async with AsyncSessionLocal() as db:
                reach = await campaign_reach(db, await db.get(Campaign, camp_id))
            assert reach["total"] == 3
            assert reach["web"] == 1
            assert reach["whatsapp"] == 2
            assert reach["whatsapp_cost_mxn"] == round(2 * META_MARKETING_USD_MX * USD_TO_MXN, 2)
            assert reach["web_supported"] is True
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_radio_campaign_is_whatsapp_only(self):
        user_id, (with_push, _) = await _seed(2)
        try:
            await _add_subs(user_id, with_push, 1)
            camp_id = await _campaign(user_id, mode="radio")
            async with AsyncSessionLocal() as db:
                reach = await campaign_reach(db, await db.get(Campaign, camp_id))
            assert reach == {"total": 2, "web": 0, "whatsapp": 2,
                             "whatsapp_cost_mxn": round(2 * META_MARKETING_USD_MX * USD_TO_MXN, 2),
                             "web_supported": False}
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_preview_endpoint_is_scoped_to_the_owner(self):
        user_id, (cid,) = await _seed(1)
        other_id, _ = await _seed(0)
        try:
            camp_id = await _campaign(user_id)
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, user_id)
                assert (await campaign_reach_preview(camp_id, db=db, current_user=owner))["total"] == 1
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc:
                    await campaign_reach_preview(camp_id, db=db, current_user=other)
                assert exc.value.status_code == 404
        finally:
            await _cleanup(user_id)
            await _cleanup(other_id)


class TestWebOnlySend:
    @pytest.mark.asyncio
    async def test_web_only_never_touches_whatsapp(self):
        from app.workers.task_helpers.campaign_ops import send_regular_messages
        user_id, (with_push, without) = await _seed()
        try:
            camp_id = await _campaign(user_id)
            async with AsyncSessionLocal() as db:
                camp = await db.get(Campaign, camp_id)
                camp.ab_test = {**camp.ab_test, "web_only": True}
                await db.commit()
            pushed = []

            async def fake_push(db, contact_id, **kw):
                pushed.append(contact_id)
                return 1

            whatsapp = MagicMock()
            offer = AsyncMock(return_value=("open", None))
            with patch("app.workers.task_helpers.campaign_ops.contacts_with_push", AsyncMock(return_value={with_push})), \
                 patch("app.services.web_push.push_to_contact", side_effect=fake_push), \
                 patch("app.workers.task_helpers.campaign_ops._offer_or_queue", offer), \
                 patch("app.workers.tasks.send_whatsapp_message.apply_async", whatsapp), \
                 patch("app.core.email.send_campaign_sent_email", AsyncMock()):
                async with AsyncSessionLocal() as db:
                    camp = await db.get(Campaign, camp_id)
                    user = await db.get(User, user_id)
                    contacts = [await db.get(Contact, with_push), await db.get(Contact, without)]
                    await send_regular_messages(db, camp, contacts, user, {}, [], ban_delay=0)

            assert pushed == [with_push]
            assert whatsapp.call_count == 0
            assert offer.await_count == 0  # ni siquiera la invitación con plantilla
            async with AsyncSessionLocal() as db:
                assert (await db.get(User, user_id)).messages_remaining == 5
        finally:
            await _cleanup(user_id)


class TestResumeWebOnly:
    @pytest.mark.asyncio
    async def test_rejected_when_nobody_has_notifications(self):
        user_id, _ = await _seed(2)
        try:
            camp_id = await _campaign(user_id)
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc:
                    await resume_campaign(camp_id, _request(), ResumeBody(web_only=True), db=db,
                                          current_user=user, _=None, redis=None)
            assert exc.value.status_code == 409
            assert "notificaciones" in exc.value.detail
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_rejected_for_radio(self):
        user_id, (cid,) = await _seed(1)
        try:
            await _add_subs(user_id, cid, 1)
            camp_id = await _campaign(user_id, mode="radio")
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc:
                    await resume_campaign(camp_id, _request(), ResumeBody(web_only=True), db=db,
                                          current_user=user, _=None, redis=None)
            assert exc.value.status_code == 400
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_sends_without_whatsapp_balance_and_remembers_choice(self):
        user_id, (cid, _) = await _seed(2)
        try:
            await _add_subs(user_id, cid, 1)
            camp_id = await _campaign(user_id, messages_remaining=0)
            delay = MagicMock()
            with patch("app.api.v1.campaigns.schedule_campaign.delay", delay):
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    await resume_campaign(camp_id, _request(), ResumeBody(web_only=True), db=db,
                                          current_user=user, _=None, redis=None)
            delay.assert_called_once_with(str(camp_id))
            async with AsyncSessionLocal() as db:
                camp = await db.get(Campaign, camp_id)
                assert camp.status == "running"
                assert camp.ab_test == {"campaign_mode": "regular", "web_only": True}
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_normal_send_clears_an_old_web_only(self):
        user_id, (cid,) = await _seed(1)
        try:
            camp_id = await _campaign(user_id)
            async with AsyncSessionLocal() as db:
                camp = await db.get(Campaign, camp_id)
                camp.ab_test = {**camp.ab_test, "web_only": True}
                camp.status = "paused"
                await db.commit()
            with patch("app.api.v1.campaigns.schedule_campaign.delay", MagicMock()):
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    await resume_campaign(camp_id, _request(), None, db=db, current_user=user, _=None, redis=None)
            async with AsyncSessionLocal() as db:
                assert "web_only" not in (await db.get(Campaign, camp_id)).ab_test
        finally:
            await _cleanup(user_id)
