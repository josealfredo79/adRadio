"""Campaña en 3 toques (docs/specs/2026-10-28-campana-3-toques.md): grupos
"los que compraron" (90 días) y "uno", alcance antes de guardar, "solo por web"
que deja la promo en el chat de quien no tiene avisos, y búsqueda de clientes.
El push y WhatsApp reales nunca se tocan."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.api.v1.campaigns import (
    ReachPreviewBody,
    ResumeBody,
    campaign_reach_before_create,
    create_campaign,
    resume_campaign,
)
from app.api.v1.contacts import list_contacts
from app.database import AsyncSessionLocal
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.coupon import Coupon
from app.models.message import Message
from app.models.sale import Sale
from app.models.user import User
from app.schemas.campaign import CampaignCreate
from app.services.campaign_reach import recipients_query
from app.workers.task_helpers.campaign_ops import segment_fingerprint
from tests.test_campaign_reach import _campaign
from tests.test_web_push import (  # noqa: F401 — _keys es fixture autouse
    _add_subs,
    _cleanup,
    _keys,
    _seed,
)


def _request(path: str = "/api/v1/campaigns") -> Request:
    return Request({"type": "http", "method": "POST", "path": path,
                    "headers": [], "client": ("test", 1), "query_string": b""})


async def _sale(user_id, contact_id, days_ago: int, source: str = "counter"):
    async with AsyncSessionLocal() as db:
        db.add(Sale(advertiser_id=user_id, contact_id=contact_id, amount=Decimal(120), source=source,
                    source_key=str(contact_id) if source == "order" else "",
                    created_at=datetime.now(timezone.utc) - timedelta(days=days_ago)))
        await db.commit()


async def _recipients(segment: dict, user_id) -> set:
    async with AsyncSessionLocal() as db:
        camp = Campaign(advertiser_id=user_id, name="", type="promo", message_text="", segment=segment)
        return {c.id for c in (await db.execute(recipients_query(camp))).scalars().all()}


class TestWhoGetsIt:
    @pytest.mark.asyncio
    async def test_caso4_todos_va_a_todos_los_activos(self):
        user_id, ids = await _seed(3)
        try:
            async with AsyncSessionLocal() as db:
                (await db.get(Contact, ids[2])).status = "unsubscribed"
                await db.commit()
            assert await _recipients({}, user_id) == {ids[0], ids[1]}
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso5_los_que_compraron_en_90_dias(self):
        user_id, (reciente, viejo, pedido, nunca) = await _seed(4)
        try:
            await _sale(user_id, reciente, days_ago=10)
            await _sale(user_id, viejo, days_ago=120)
            await _sale(user_id, pedido, days_ago=30, source="order")
            assert await _recipients({"bought_days": 90}, user_id) == {reciente, pedido}
            assert nunca not in await _recipients({"bought_days": 90}, user_id)
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso5_sin_compradores_el_alcance_es_cero(self):
        user_id, _ = await _seed(2)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                reach = await campaign_reach_before_create(_request(), ReachPreviewBody(segment={"bought_days": 90}),
                                                           db=db, current_user=user)
            assert reach["total"] == 0 and reach["web_chat"] == 0
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso5_dias_invalidos_se_rechazan(self):
        user_id, _ = await _seed(0)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                bads = [{"bought_days": b} for b in (0, 400, "90", True)] + [{"specific_contacts": ["no-es-id"]}]
                for bad in bads:
                    with pytest.raises(HTTPException) as exc:
                        await campaign_reach_before_create(_request(), ReachPreviewBody(segment=bad),
                                                           db=db, current_user=user)
                    assert exc.value.status_code == 422
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso6_uno_solo(self):
        user_id, ids = await _seed(3)
        try:
            assert await _recipients({"specific_contacts": [str(ids[1])]}, user_id) == {ids[1]}
        finally:
            await _cleanup(user_id)

    def test_compradores_cuentan_aparte_para_la_pausa_de_7_dias(self):
        # Los grupos de antes conservan su huella; "compraron" no se confunde con "todos".
        import hashlib
        import json
        old = hashlib.sha256(json.dumps({"specific_contacts": [], "tags": []}, sort_keys=True).encode()).hexdigest()
        assert segment_fingerprint({}) == old
        assert segment_fingerprint({"bought_days": 90}) != old
        # Cambiar los días no da otra lista (no se salta la pausa).
        assert segment_fingerprint({"bought_days": 30}) == segment_fingerprint({"bought_days": 90})


class TestReachPreview:
    @pytest.mark.asyncio
    async def test_caso7_cuenta_aviso_chat_y_whatsapp_sin_guardar(self):
        user_id, (con_avisos, _) = await _seed(2)
        try:
            await _add_subs(user_id, con_avisos, 1)
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                reach = await campaign_reach_before_create(_request(), ReachPreviewBody(), db=db, current_user=user)
            assert (reach["web"], reach["web_chat"]) == (1, 1)
            async with AsyncSessionLocal() as db:
                n = (await db.execute(select(Campaign).where(Campaign.advertiser_id == user_id))).all()
            assert n == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso8_sin_chip_nadie_por_whatsapp(self):
        user_id, _ = await _seed(2)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                reach = await campaign_reach_before_create(_request(), ReachPreviewBody(), db=db, current_user=user)
            assert reach["whatsapp_connected"] is False
            assert reach["whatsapp"] == 0 and reach["whatsapp_unreachable"] == 2
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso9_con_chip_cuenta_whatsapp_y_costo(self):
        user_id, _ = await _seed(2)
        try:
            await _campaign(user_id, connected=True)  # deja el WhatsApp propio conectado
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                reach = await campaign_reach_before_create(_request(), ReachPreviewBody(), db=db, current_user=user)
            assert reach["whatsapp_connected"] is True
            assert reach["whatsapp"] == 2 and reach["whatsapp_cost_mxn"] > 0
        finally:
            await _cleanup(user_id)


class TestWebOnlyLeavesItInTheChat:
    async def _send_web_only(self, user_id, camp_id, contact_ids, push_ids):
        from app.workers.task_helpers.campaign_ops import send_regular_messages
        pushed = []

        async def fake_push(db, contact_id, **kw):
            pushed.append(contact_id)
            return 1

        whatsapp = MagicMock()
        with patch("app.workers.task_helpers.campaign_ops.contacts_with_push", AsyncMock(return_value=set(push_ids))), \
             patch("app.services.web_push.push_to_contact", side_effect=fake_push), \
             patch("app.workers.tasks.send_whatsapp_message.apply_async", whatsapp), \
             patch("app.workers.tasks.send_whatsapp_voice_note.apply_async", whatsapp):
            async with AsyncSessionLocal() as db:
                camp = await db.get(Campaign, camp_id)
                camp.ab_test = {**camp.ab_test, "web_only": True}
                user = await db.get(User, user_id)
                contacts = [await db.get(Contact, c) for c in contact_ids]
                await send_regular_messages(db, camp, contacts, user, camp.ab_test, [], ban_delay=0)
                await db.commit()
        return pushed, whatsapp

    @pytest.mark.asyncio
    async def test_caso10_suena_a_quien_tiene_avisos_y_queda_en_el_chat_de_los_demas(self):
        user_id, (con_avisos, sin_avisos) = await _seed(2)
        try:
            camp_id = await _campaign(user_id)
            pushed, whatsapp = await self._send_web_only(user_id, camp_id, [con_avisos, sin_avisos], [con_avisos])
            assert pushed == [con_avisos] and whatsapp.call_count == 0
            async with AsyncSessionLocal() as db:
                rows = dict((await db.execute(
                    select(Message.contact_id, Message.content).where(Message.campaign_id == camp_id)
                )).all())
                assert rows == {con_avisos: "[PUSH] 2x1 en cortes", sin_avisos: "[WEB] 2x1 en cortes"}
                assert (await db.get(User, user_id)).messages_remaining == 5
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso11_con_descuento_cada_cliente_tiene_su_cupon(self):
        user_id, ids = await _seed(2)
        try:
            camp_id = await _campaign(user_id)
            async with AsyncSessionLocal() as db:
                camp = await db.get(Campaign, camp_id)
                camp.ab_test = {**camp.ab_test, "has_coupon": True, "coupon_description": "15% de descuento"}
                await db.commit()
            await self._send_web_only(user_id, camp_id, ids, [ids[0]])
            async with AsyncSessionLocal() as db:
                coupons = (await db.execute(select(Coupon).where(Coupon.campaign_id == camp_id))).scalars().all()
            assert {c.contact_id for c in coupons} == set(ids)
            assert {c.description for c in coupons} == {"15% de descuento"}
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso11_aviso_que_falla_queda_en_el_chat_con_un_solo_cupon(self):
        from app.workers.task_helpers.campaign_ops import send_regular_messages
        user_id, (cid,) = await _seed(1)
        try:
            camp_id = await _campaign(user_id)
            async with AsyncSessionLocal() as db:
                camp = await db.get(Campaign, camp_id)
                camp.ab_test = {**camp.ab_test, "web_only": True, "has_coupon": True}
                await db.commit()
            with patch("app.workers.task_helpers.campaign_ops.contacts_with_push", AsyncMock(return_value={cid})), \
                 patch("app.services.web_push.push_to_contact", AsyncMock(return_value=0)):
                async with AsyncSessionLocal() as db:
                    camp = await db.get(Campaign, camp_id)
                    await send_regular_messages(db, camp, [await db.get(Contact, cid)], await db.get(User, user_id),
                                                camp.ab_test, [], ban_delay=0)
                    await db.commit()
            async with AsyncSessionLocal() as db:
                msgs = (await db.execute(select(Message.content).where(Message.campaign_id == camp_id))).scalars().all()
                coupons = (await db.execute(select(Coupon).where(Coupon.campaign_id == camp_id))).scalars().all()
            assert msgs == ["[WEB] 2x1 en cortes"] and len(coupons) == 1
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso11_sin_descuento_no_hay_cupon(self):
        user_id, ids = await _seed(2)
        try:
            camp_id = await _campaign(user_id)
            await self._send_web_only(user_id, camp_id, ids, [ids[0]])
            async with AsyncSessionLocal() as db:
                assert (await db.execute(select(Coupon).where(Coupon.campaign_id == camp_id))).all() == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso13_solo_por_web_se_manda_aunque_nadie_tenga_avisos(self):
        user_id, _ = await _seed(2)
        try:
            camp_id = await _campaign(user_id, connected=False)
            delay = MagicMock()
            with patch("app.api.v1.campaigns.schedule_campaign.delay", delay):
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    await resume_campaign(camp_id, _request(), ResumeBody(web_only=True), db=db,
                                          current_user=user, _=None, redis=None)
            delay.assert_called_once_with(str(camp_id))
        finally:
            await _cleanup(user_id)


class TestCreateAndSearch:
    @pytest.mark.asyncio
    async def test_caso12_sin_plan_activo_no_crea_y_dice_por_que(self):
        user_id, _ = await _seed(0)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                user.subscription_status = "canceled"
                await db.commit()
                body = CampaignCreate(name="2x1", type="promo", message_text="2x1 en tacos",
                                      segment={"bought_days": 90})
                with pytest.raises(HTTPException) as exc:
                    await create_campaign(_request(), body, db=db, current_user=user, _=None, redis=None)
            assert exc.value.status_code == 402 and "plan activo" in exc.value.detail
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso6_busca_cliente_por_nombre_o_telefono(self):
        user_id, ids = await _seed(3)
        try:
            async with AsyncSessionLocal() as db:
                c = await db.get(Contact, ids[1])
                c.name, c.phone = "Doña Lupe", "+5219531234567"
                await db.commit()
                user = await db.get(User, user_id)
                for term in ("lupe", "1234567"):
                    res = await list_contacts(page=1, page_size=20, status_filter=None, tag=None, search=term,
                                              db=db, current_user=user)
                    assert [i.id for i in res.items] == [ids[1]]
        finally:
            await _cleanup(user_id)
