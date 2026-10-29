"""Campañas Fase A (docs/specs/2026-10-28-campanas-fase-a.md): los 7 estilos de
audio llegan como la cuña que el dueño escuchó (web y WhatsApp), el tope de
cuñas por mes sí frena, y Arranque tiene 1 audio y 1 imagen de prueba al mes.
Base y Redis reales; el push del navegador y WhatsApp son falsos."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from starlette.requests import Request

from app.api.v1.campaigns import (
    BannerPreviewRequest,
    create_campaign,
    generate_radio_ad_endpoint,
    preview_banner,
)
from app.api.v1.portal import _promo_audio
from app.database import AsyncSessionLocal, engine
from app.domain.campaign_actions import RADIO_MODES
from app.models.campaign import Campaign
from app.models.message import Message
from app.models.user import User
from app.schemas.campaign import CampaignCreate, GenerateRadioAdRequest
from app.services.campaign_quota import quota_block, quota_summary
from app.services.campaign_reach import campaign_reach
from app.services.send_block_explain import preflight_campaign_send
from tests.test_web_push import (  # noqa: F401 — _keys es fixture autouse
    _add_subs,
    _cleanup,
    _keys,
    _seed,
)

AUDIO = "https://cdn.test/cuna.ogg"


@pytest.fixture(autouse=True)
def _count_from_past(monkeypatch):
    # El tope cuenta desde el día de la subida; en las pruebas, desde antes.
    from app.services import campaign_quota
    monkeypatch.setattr(campaign_quota, "COUNT_FROM", datetime(2020, 1, 1, tzinfo=timezone.utc))


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/campaigns",
                    "headers": [], "client": ("test", 1), "query_string": b""})


async def _plan(user_id, plan: str, connected: bool = False):
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        user.current_plan = plan
        user.subscription_status = "active"
        user.messages_remaining = 50
        if connected:
            user.meta_connection_status = "connected"
            user.meta_phone_number_id = "123456"
            user.meta_token_cipher, user.meta_token_iv, user.meta_token_tag = "c", "iv", "tag"
        await db.commit()


async def _camp(user_id, mode: str, status: str = "draft", web_only: bool = True, days_ago: int = 0):
    async with AsyncSessionLocal() as db:
        ab = {"campaign_mode": mode}
        if mode in RADIO_MODES:
            ab.update(audio_url=AUDIO, radio_script="Este dato te lo trae CityCell")
        if web_only:
            ab["web_only"] = True
        camp = Campaign(advertiser_id=user_id, name=f"Promo {mode}", type="promo", status=status,
                        message_text="2x1 en micas", segment={}, ab_test=ab,
                        image_url="https://cdn.test/b.png" if mode == "banner" else None)
        db.add(camp)
        await db.flush()
        if days_ago:
            camp.created_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
        await db.commit()
        return camp.id


# ── Casos 1 y 2: los 7 estilos se mandan como cuña ─────────────────────────────

@pytest.mark.parametrize("mode", RADIO_MODES)
def test_caso1_los_7_estilos_llegan_por_web_con_la_cuna(mode):
    user_id, (with_push, without) = asyncio.run(_seed(2))
    try:
        async def setup():
            await engine.dispose()  # cada asyncio.run trae su propio loop
            await _plan(user_id, "growth")
            await _add_subs(user_id, with_push, 1)
            return await _camp(user_id, mode, status="scheduled")
        camp_id = asyncio.run(setup())

        from app.workers import tasks
        push = AsyncMock(return_value=1)
        whatsapp = MagicMock()
        with patch("app.services.messaging_throttle.is_human_hour", return_value=True), \
             patch("app.services.web_push.push_to_contact", push), \
             patch.object(tasks, "send_whatsapp_voice_note", whatsapp), \
             patch.object(tasks, "send_whatsapp_message", whatsapp):
            tasks.schedule_campaign(str(camp_id))
        whatsapp.apply_async.assert_not_called()
        push.assert_awaited_once()
        assert push.await_args.kwargs["body"].startswith(f"Promo {mode} — 🔊 Toca para escucharla.")

        async def after():
            await engine.dispose()
            async with AsyncSessionLocal() as db:
                camp = await db.get(Campaign, camp_id)
                msgs = (await db.execute(select(Message.contact_id, Message.content)
                                         .where(Message.campaign_id == camp_id))).all()
                return camp, dict(msgs)
        camp, msgs = asyncio.run(after())
        assert msgs == {with_push: f"[PUSH] Promo {mode}", without: f"[WEB] Promo {mode}"}
        assert _promo_audio(camp) == AUDIO  # la tarjeta del cliente trae la cuña que escuchó el dueño
    finally:
        asyncio.run(_cleanup(user_id))


@pytest.mark.parametrize("mode", RADIO_MODES)
def test_caso2_por_whatsapp_sale_la_misma_cuna_no_el_texto(mode):
    user_id, _ = asyncio.run(_seed(1))
    try:
        async def setup():
            await engine.dispose()  # cada asyncio.run trae su propio loop
            await _plan(user_id, "growth", connected=True)
            return await _camp(user_id, mode, status="scheduled", web_only=False)
        camp_id = asyncio.run(setup())

        from app.workers import tasks
        radio, regular = AsyncMock(), AsyncMock()
        with patch("app.services.messaging_throttle.is_human_hour", return_value=True), \
             patch.object(tasks, "send_radio_messages", radio), \
             patch.object(tasks, "send_regular_messages", regular):
            tasks.schedule_campaign(str(camp_id))
        radio.assert_awaited_once()
        regular.assert_not_awaited()
        assert radio.await_args.args[4]["audio_url"] == AUDIO  # ab con la cuña
    finally:
        asyncio.run(_cleanup(user_id))


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", RADIO_MODES)
async def test_caso3_el_alcance_cuenta_la_web_en_los_7_estilos(mode):
    user_id, (cid, _) = await _seed(2)
    try:
        await _add_subs(user_id, cid, 1)
        camp_id = await _camp(user_id, mode)
        async with AsyncSessionLocal() as db:
            reach = await campaign_reach(db, await db.get(Campaign, camp_id))
        assert reach["web_supported"] is True
        assert (reach["web"], reach["web_chat"]) == (1, 1)
    finally:
        await _cleanup(user_id)


# ── Caso 4: el tope de cuñas por mes sí frena ─────────────────────────────────

@pytest.mark.asyncio
async def test_caso4_negocio_la_quinta_cuna_del_mes_no_se_genera():
    user_id, _ = await _seed(0)
    try:
        await _plan(user_id, "growth")
        for mode in ("radio", "capsula", "trivia"):
            await _camp(user_id, mode, status="completed")
        await _camp(user_id, "historia", status="draft")              # borrador: no cuenta
        await _camp(user_id, "alerta", status="completed", days_ago=31)  # mes pasado: no cuenta
        async with AsyncSessionLocal() as db:
            assert await quota_block(db, await db.get(User, user_id), "audio") is None  # van 3 de 4

        await _camp(user_id, "estacional", status="completed")
        body = GenerateRadioAdRequest(business_name="CityCell", intent="2x1 en micas")
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            with pytest.raises(HTTPException) as exc:
                await generate_radio_ad_endpoint(body, current_user=user, db=db)
        assert exc.value.status_code == 402
        assert exc.value.detail.startswith("Ya usaste las 4 cuñas de radio de tu plan este mes")
    finally:
        await _cleanup(user_id)


# ── Casos 5 y 6: Arranque, 1 audio y 1 imagen de prueba al mes ─────────────────

@pytest.mark.asyncio
async def test_caso5_arranque_manda_un_audio_de_prueba_y_el_segundo_no():
    user_id, _ = await _seed(1)
    try:
        await _plan(user_id, "starter")
        first = await _camp(user_id, "capsula")
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            assert await quota_block(db, user, "audio") is None
            assert await preflight_campaign_send(db, await db.get(Campaign, first), user, web_only=True) is None
            (await db.get(Campaign, first)).status = "completed"
            await db.commit()

        second = await _camp(user_id, "radio")
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            reason = await preflight_campaign_send(db, await db.get(Campaign, second), user, web_only=True)
            assert reason == "Tu audio de prueba de este mes ya lo usaste. El audio es del plan Negocio (4 al mes)."
            # Reanudar la que ya salió no se frena a sí misma.
            camp = await db.get(Campaign, first)
            camp.status = "paused"
            await db.commit()
            assert await preflight_campaign_send(db, camp, user, web_only=True) is None
            with pytest.raises(HTTPException) as exc:
                await generate_radio_ad_endpoint(GenerateRadioAdRequest(business_name="CityCell", intent="x"),
                                                 current_user=user, db=db)
            assert exc.value.status_code == 402 and "audio de prueba" in exc.value.detail
            assert (await quota_summary(db, user))["audio"] == {"limit": 1, "used": 1, "trial": True}
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso6_arranque_una_imagen_de_prueba_y_la_vista_previa_siempre():
    user_id, _ = await _seed(1)
    try:
        await _plan(user_id, "starter")
        body = CampaignCreate(name="2x1 micas", type="promo", message_text="2x1 en micas",
                              ab_test={"campaign_mode": "banner"})
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            created = await create_campaign(_request(), body, db=db, current_user=user, _=None, redis=None)
            camp = await db.get(Campaign, created.id)
            camp.status = "completed"
            await db.commit()

            with patch("app.api.v1.campaigns.generate_banner_copy_with_claude", AsyncMock(return_value={})), \
                 patch("app.api.v1.campaigns.generate_banner_png", return_value=b"png"):
                out = await preview_banner(BannerPreviewRequest(promo_description="2x1", business_name="CityCell"),
                                           current_user=user)
            assert out.body == b"png"  # la vista previa se ve aunque ya usó la de prueba

            with pytest.raises(HTTPException) as exc:
                await create_campaign(_request(), body, db=db, current_user=user, _=None, redis=None)
            assert exc.value.status_code == 402
            assert exc.value.detail == "Tu imagen de prueba de este mes ya la usaste. Las imágenes son del plan Negocio."
            assert (await quota_summary(db, user))["image"] == {"limit": 1, "used": 1, "trial": True}
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_caso6_desde_negocio_las_imagenes_no_tienen_tope():
    user_id, _ = await _seed(0)
    try:
        await _plan(user_id, "growth")
        for _ in range(3):
            await _camp(user_id, "banner", status="completed")
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            assert await quota_block(db, user, "image") is None
            assert (await quota_summary(db, user))["image"]["limit"] == -1
    finally:
        await _cleanup(user_id)


# ── Huecos que encontró revisor-dinero ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_no_se_salta_el_tope_creando_la_cuna_ya_programada_ni_por_envio_masivo():
    from app.api.v1.contacts import BulkSendCampaignRequest, bulk_send_campaign

    user_id, (cid,) = await _seed(1)
    try:
        await _plan(user_id, "starter")
        await _camp(user_id, "radio", status="completed")  # ya usó la de prueba
        body = CampaignCreate(name="Otra cuña", type="promo", message_text="x", status="scheduled",
                              ab_test={"campaign_mode": "capsula", "audio_url": AUDIO})
        draft = await _camp(user_id, "trivia")
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            with pytest.raises(HTTPException) as exc:
                await create_campaign(_request(), body, db=db, current_user=user, _=None, redis=None)
            assert exc.value.status_code == 402 and "audio de prueba" in exc.value.detail
            delay = MagicMock()
            with patch("app.workers.tasks.schedule_campaign.delay", delay), pytest.raises(HTTPException) as exc:
                await bulk_send_campaign(_request(), BulkSendCampaignRequest(contact_ids=[str(cid)], campaign_id=str(draft)),
                                         db=db, current_user=user)
            assert exc.value.status_code == 409 and "audio de prueba" in exc.value.detail
            delay.assert_not_called()
    finally:
        await _cleanup(user_id)


@pytest.mark.asyncio
async def test_la_parrilla_y_lo_de_antes_de_la_subida_no_cuentan(monkeypatch):
    from app.services import campaign_quota

    user_id, _ = await _seed(0)
    try:
        await _plan(user_id, "starter")
        async with AsyncSessionLocal() as db:
            db.add(Campaign(advertiser_id=user_id, name="Parrilla: Lunes", type="promo", status="scheduled",
                            message_text="x", segment={}, ab_test={"campaign_mode": "radio", "audio_url": AUDIO}))
            await db.commit()
        old = await _camp(user_id, "radio", status="completed", days_ago=2)
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            assert await campaign_quota.used_this_month(db, user, "audio") == 1  # la de hace 2 días; la parrilla no
            camp = await db.get(Campaign, old)
            monkeypatch.setattr(campaign_quota, "COUNT_FROM", datetime.now(timezone.utc) - timedelta(days=1))
            assert await campaign_quota.used_this_month(db, user, "audio") == 0  # salió antes de la subida
            assert camp.status == "completed"
    finally:
        await _cleanup(user_id)
