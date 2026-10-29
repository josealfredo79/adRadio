"""El Copiloto crea y manda promos (docs/specs/2026-10-28-copiloto-crea-promos.md).
Base y Redis reales; la IA (generador de promos y la cadena del Copiloto),
el push y WhatsApp siempre simulados."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select
from starlette.requests import Request

from app.database import AsyncSessionLocal, engine
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.sale import Sale
from app.models.user import User
from app.services import copilot_promo_tools as promo
from app.services import copilot_service as cs
from app.services import copilot_whatsapp_service as cw
from app.services import llm_client

GEN = "app.services.claude_service.generate_campaign_variants"
DELAY = "app.workers.tasks.schedule_campaign.delay"
TEXT = "¡Hola {{nombre}}! Este viernes 2x1 en fundas en CityCell: funda antigolpes $220."


async def _seed(n_contacts: int = 3, connected: bool = False, **user_kw):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="CityCell",
                    subscription_status=user_kw.pop("subscription_status", "active"), messages_remaining=50, **user_kw)
        if connected:
            user.meta_connection_status = "connected"
            user.meta_phone_number_id = "123"
            user.meta_token_cipher, user.meta_token_iv, user.meta_token_tag = "c", "i", "t"
        db.add(user)
        await db.flush()
        names = ["Doña Lupe", "Pedro Ramírez", "Lupita Cruz", "Ana Torres"][:n_contacts]
        contacts = [Contact(advertiser_id=user.id, name=n, phone=f"+52155{uuid.uuid4().int % 10**8:08d}") for n in names]
        db.add_all(contacts)
        await db.commit()
        return user.id, [c.id for c in contacts]


async def _cleanup(user_id):
    from app.models.coupon import Coupon
    from app.models.message import Message
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for model in (Coupon, Message, Campaign, Sale, Contact):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.execute(delete(User).where(User.id == user_id))
        await db.commit()
    await engine.dispose()


async def _preview(user_id, **args):
    with patch(GEN, AsyncMock(return_value=[TEXT, "otra"])) as gen:
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            out = await promo.preview(db, user, {"what": "2x1 en fundas este viernes", **args})
    return (*out, gen)


async def _confirm(user_id, resolved):
    delay = MagicMock()
    with patch(DELAY, delay):
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            data, error = await promo.execute(db, user, resolved)
    return data, error, delay


async def _campaigns(user_id):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Campaign).where(Campaign.advertiser_id == user_id))).scalars().all()


class TestPreview:
    @pytest.mark.asyncio
    async def test_caso1_ensena_el_mensaje_con_catalogo_a_quien_y_por_donde(self):
        user_id, _ = await _seed(3)
        try:
            summary, resolved, error, gen = await _preview(user_id)
            assert error is None
            assert TEXT in summary and "todos tus clientes" in summary
            assert "3 clientes la ven en su chat" in summary and "gratis por web" in summary
            assert gen.await_args.kwargs["intent"] == "2x1 en fundas este viernes"
            assert {k: v for k, v in resolved.items() if k != "key"} == {
                "name": "2x1 en fundas este viernes", "message": TEXT, "segment": {}, "discount_percent": 0, "web_only": True,
            }
            # A quién y por dónde van antes del mensaje (WhatsApp corta en 1024 caracteres).
            assert summary.index("Le llega") < summary.index(TEXT)
            assert await _campaigns(user_id) == []  # la vista previa no guarda nada
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso1_el_catalogo_real_llega_al_generador(self):
        from app.models.product import Product
        user_id, _ = await _seed(1)
        try:
            async with AsyncSessionLocal() as db:
                db.add(Product(advertiser_id=user_id, name="Funda antigolpes", price=Decimal(220)))
                await db.commit()
            *_, gen = await _preview(user_id)
            assert "Funda antigolpes" in gen.await_args.kwargs["catalog"] and "$220" in gen.await_args.kwargs["catalog"]
        finally:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(Product).where(Product.advertiser_id == user_id))
                await db.commit()
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso3_pide_whatsapp_sin_chip_va_solo_por_web(self):
        user_id, _ = await _seed(2, connected=False)
        try:
            summary, resolved, error, _ = await _preview(user_id, whatsapp=True)
            assert error is None and resolved["web_only"] is True
            assert "no está conectado" in summary and "Conecta tu chip" in summary
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso4_pide_whatsapp_con_chip_dice_el_costo(self):
        user_id, _ = await _seed(2, connected=True)
        try:
            summary, resolved, _, _ = await _preview(user_id, whatsapp=True)
            assert resolved["web_only"] is False
            assert "2 clientes por WhatsApp (Meta te cobra aprox $" in summary
            # Sin pedir WhatsApp, aunque tenga chip, va gratis por web.
            summary, resolved, _, _ = await _preview(user_id)
            assert resolved["web_only"] is True and "por WhatsApp" not in summary
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso5_descuento_solo_si_lo_pide(self):
        user_id, _ = await _seed(1)
        try:
            summary, resolved, _, _ = await _preview(user_id, discount_percent=15)
            assert resolved["discount_percent"] == 15 and "cupón de 15%" in summary
            summary, resolved, _, _ = await _preview(user_id)
            assert resolved["discount_percent"] == 0 and "cupón" not in summary
            _, _, error, _ = await _preview(user_id, discount_percent=150)
            assert "1% a 90%" in error
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso6_los_que_compraron_y_uno_por_nombre(self):
        user_id, (lupe, pedro, _) = await _seed(3)
        try:
            async with AsyncSessionLocal() as db:
                db.add(Sale(advertiser_id=user_id, contact_id=pedro, amount=Decimal(100),
                            created_at=datetime.now(timezone.utc) - timedelta(days=5)))
                await db.commit()
            summary, resolved, _, _ = await _preview(user_id, audience="bought")
            assert resolved["segment"] == {"bought_days": 90} and "1 cliente la ve en su chat" in summary
            summary, resolved, _, _ = await _preview(user_id, audience="one", contact="Pedro")
            assert resolved["segment"] == {"specific_contacts": [str(pedro)]} and "Pedro Ramírez" in summary
            # Nombre exacto gana aunque otro lo contenga ("Lupita Cruz").
            _, resolved, _, _ = await _preview(user_id, audience="one", contact="Doña Lupe")
            assert resolved["segment"] == {"specific_contacts": [str(lupe)]}
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso6_nombre_que_no_existe_o_varios_no_manda(self):
        user_id, _ = await _seed(3)
        try:
            _, resolved, error, gen = await _preview(user_id, audience="one", contact="Chucho")
            assert resolved is None and "No encontré a «Chucho»" in error
            gen.assert_not_awaited()  # ni gasta IA
            _, resolved, error, _ = await _preview(user_id, audience="one", contact="lup")
            assert resolved is None and "Hay varios" in error and "Doña Lupe" in error and "Lupita Cruz" in error
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso7_cambio_usa_el_texto_corregido_sin_volver_a_generar(self):
        user_id, _ = await _seed(1)
        try:
            summary, resolved, _, gen = await _preview(user_id, message="2x1 en fundas, solo este viernes.")
            gen.assert_not_awaited()
            assert resolved["message"] == "2x1 en fundas, solo este viernes." and "solo este viernes" in summary
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso9_nadie_a_quien_dice_por_que(self):
        user_id, _ = await _seed(0)
        try:
            _, resolved, error, _ = await _preview(user_id)
            assert resolved is None and "no tienes clientes" in error
            user2, _ = await _seed(2)
            _, resolved, error, _ = await _preview(user2, audience="bought")
            assert resolved is None and "Nadie te ha comprado en los últimos 90 días" in error
            await _cleanup(user2)
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso11_sin_plan_activo_no_crea(self):
        user_id, _ = await _seed(2, subscription_status="churned")
        try:
            _, resolved, error, gen = await _preview(user_id)
            assert resolved is None and "plan activo" in error
            gen.assert_not_awaited()
        finally:
            await _cleanup(user_id)


class TestConfirm:
    @pytest.mark.asyncio
    async def test_caso2_si_crea_la_campana_y_sale_gratis_por_web(self):
        user_id, _ = await _seed(2)
        try:
            _, resolved, _, _ = await _preview(user_id)
            data, error, delay = await _confirm(user_id, resolved)
            assert error is None and data["web_only"] is True
            (camp,) = await _campaigns(user_id)
            assert (camp.name, camp.type, camp.status, camp.message_text) == ("2x1 en fundas este viernes", "promo", "running", TEXT)
            assert camp.ab_test == {"enabled": False, "campaign_mode": "regular", "web_only": True,
                                    "copilot_key": resolved["key"]}
            delay.assert_called_once_with(str(camp.id))
            async with AsyncSessionLocal() as db:
                assert (await db.get(User, user_id)).messages_remaining == 50
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("label", [None, "mañana a las 8:00 a. m."])
    async def test_de_noche_dice_cuando_sale_en_vez_de_enviada(self, label):
        user_id, _ = await _seed(2)
        try:
            _, resolved, _, _ = await _preview(user_id)
            with patch("app.services.messaging_throttle.send_starts_label", return_value=label):
                data, error, _ = await _confirm(user_id, resolved)
            assert error is None
            if label:
                assert data["sale"].startswith("mañana a las 8:00 a. m.")
                assert "sale mañana a las 8:00" in promo.summarize(data)
            else:
                assert "sale" not in data and "enviada" in promo.summarize(data)
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso2_el_envio_real_no_toca_whatsapp_y_deja_la_promo_en_el_chat(self):
        from app.models.message import Message
        from app.workers.task_helpers.campaign_ops import send_regular_messages
        user_id, ids = await _seed(2)
        try:
            _, resolved, _, _ = await _preview(user_id, discount_percent=15)
            await _confirm(user_id, resolved)
            (camp,) = await _campaigns(user_id)
            whatsapp = MagicMock()
            with patch("app.workers.task_helpers.campaign_ops.contacts_with_push", AsyncMock(return_value=set())), \
                 patch("app.workers.tasks.send_whatsapp_voice_note.apply_async", whatsapp), \
                 patch("app.workers.tasks.send_whatsapp_message.apply_async", whatsapp):
                async with AsyncSessionLocal() as db:
                    c = await db.get(Campaign, camp.id)
                    contacts = [await db.get(Contact, i) for i in ids]
                    await send_regular_messages(db, c, contacts, await db.get(User, user_id), c.ab_test, [], ban_delay=0)
                    await db.commit()
            assert whatsapp.call_count == 0
            from app.models.coupon import Coupon
            async with AsyncSessionLocal() as db:
                msgs = (await db.execute(select(Message.content).where(Message.campaign_id == camp.id))).scalars().all()
                coupons = (await db.execute(select(Coupon).where(Coupon.campaign_id == camp.id))).scalars().all()
            assert sorted(msgs) == ["[WEB] 2x1 en fundas este viernes"] * 2
            assert len(coupons) == 2 and {c.description for c in coupons} == {"15% de descuento"}  # caso 5
            assert {int(c.discount_value) for c in coupons} == {15}  # el % guardado, no 0
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso4_con_chip_y_whatsapp_sale_tambien_por_whatsapp(self):
        user_id, _ = await _seed(2, connected=True)
        try:
            _, resolved, _, _ = await _preview(user_id, whatsapp=True)
            data, error, delay = await _confirm(user_id, resolved)
            assert error is None and data["web_only"] is False
            (camp,) = await _campaigns(user_id)
            assert "web_only" not in camp.ab_test
            delay.assert_called_once()
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso8_confirmar_dos_veces_crea_una_sola_promo(self):
        user_id, _ = await _seed(2)
        try:
            _, resolved, _, _ = await _preview(user_id)
            data, error, _ = await _confirm(user_id, resolved)
            assert error is None
            data, error, delay = await _confirm(user_id, resolved)
            assert data is None and "ya se mandó" in error
            delay.assert_not_called()
            assert len(await _campaigns(user_id)) == 1
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso4_si_se_desconecto_el_chip_va_solo_por_web(self):
        user_id, _ = await _seed(2, connected=True)
        try:
            _, resolved, _, _ = await _preview(user_id, whatsapp=True)
            async with AsyncSessionLocal() as db:
                (await db.get(User, user_id)).meta_connection_status = "disconnected"
                await db.commit()
            data, _, _ = await _confirm(user_id, resolved)
            assert data["web_only"] is True
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso4_regla_anti_baneo_bloquea_y_queda_borrador(self):
        user_id, _ = await _seed(2, connected=True)
        try:
            _, resolved, _, _ = await _preview(user_id, whatsapp=True)
            async with AsyncSessionLocal() as db:
                (await db.get(User, user_id)).messages_remaining = 0
                await db.commit()
            data, error, delay = await _confirm(user_id, resolved)
            assert data is None and "borrador" in error
            delay.assert_not_called()
            (camp,) = await _campaigns(user_id)
            assert camp.status == "draft"
        finally:
            await _cleanup(user_id)


class TestCopilotFlow:
    def _reply(self, args):
        call = llm_client.ToolCall("t1", "send_promo", args)
        return llm_client.ToolReply("Claro, te la armo.", [call],
                                    [{"type": "tool_use", "id": "t1", "name": "send_promo", "input": args}])

    @pytest.mark.asyncio
    async def test_caso1_el_copiloto_ensena_la_vista_previa_completa_y_pide_confirmar(self):
        # La promo rápida se queda para las notas de voz (el WhatsApp escrito
        # pasó a la plática paso a paso, Fase C).
        user_id, _ = await _seed(2)
        try:
            with patch.object(llm_client, "tool_completion", AsyncMock(return_value=self._reply({"what": "2x1 en fundas"}))), \
                 patch(GEN, AsyncMock(return_value=[TEXT])), patch.object(cs, "get_redis_optional", AsyncMock(return_value=None)):
                async with AsyncSessionLocal() as db:
                    out = await cs.handle_chat(db, await db.get(User, user_id), "manda una promo de 2x1 en fundas", [],
                                               channel="voz")
            pending = out["pending_confirmation"]
            assert pending["tool"] == "send_promo"
            assert TEXT in out["reply"]  # el mensaje que se va a mandar, no el texto del modelo
            assert await _campaigns(user_id) == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso8_cancelar_no_crea_nada(self):
        user_id, _ = await _seed(2)
        try:
            with patch.object(llm_client, "tool_completion", AsyncMock(return_value=self._reply({"what": "2x1"}))), \
                 patch(GEN, AsyncMock(return_value=[TEXT])), patch.object(cs, "get_redis_optional", AsyncMock(return_value=None)):
                async with AsyncSessionLocal() as db:
                    out = await cs.handle_chat(db, await db.get(User, user_id), "manda promo 2x1", [], channel="panel")
                    await cs.handle_confirm(db, await db.get(User, user_id),
                                            out["pending_confirmation"]["confirmation_id"], False)
            assert await _campaigns(user_id) == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso8_confirmacion_vencida_no_manda(self):
        user_id, _ = await _seed(1)
        try:
            token = cs.sign_jwt({"sub": str(user_id), "tool": "send_promo", "args": {"message": "x"}, "type": "copilot_confirm"},
                                timedelta(seconds=-1))
            async with AsyncSessionLocal() as db:
                with pytest.raises((ValueError, HTTPException)):
                    await cs.handle_confirm(db, await db.get(User, user_id), token, True)
            assert await _campaigns(user_id) == []
        finally:
            await _cleanup(user_id)


class TestWhatsAppButtons:
    @pytest.mark.asyncio
    async def test_caso1_promo_trae_si_cambiar_cancelar(self):
        from tests.test_copilot_whatsapp import FakeRedis, _owner, _run
        owner, redis = _owner(), FakeRedis()
        chat = AsyncMock(return_value={"reply": "Promo…", "pending_confirmation":
                                       {"confirmation_id": "tok-9", "tool": "send_promo", "summary": "x", "args": {}}})
        *_, sb = await _run(owner, "manda una promo de 2x1", redis, chat=chat)
        assert sb.call_args.args[2] == cw.PROMO_BUTTONS
        assert [t for _, t in cw.PROMO_BUTTONS] == ["✅ Sí, mándala", "✏️ Cambiar", "❌ Cancelar"]
        assert all(len(t) <= 20 for _, t in cw.PROMO_BUTTONS)
        assert cw.parse_decision("✅ Sí, mándala") is True

    @pytest.mark.asyncio
    async def test_caso7_cambiar_no_manda_y_pregunta_que_cambiar(self):
        from tests.test_copilot_whatsapp import FakeRedis, _owner, _run
        owner, redis = _owner(), FakeRedis()
        redis.store[f"copilot_wa:{owner.id}"] = json.dumps({"history": [], "pending": "tok-9"})
        hc, hf, st, _ = await _run(owner, "✏️ Cambiar", redis)
        hf.assert_not_called()
        hc.assert_not_called()
        assert st.call_args.args[1] == cw.EDIT_PROMPT
        assert json.loads(redis.store[f"copilot_wa:{owner.id}"])["pending"] is None


class TestLaunchExisting:
    @pytest.mark.asyncio
    async def test_caso10_sin_chip_lanza_solo_por_web(self):
        user_id, _ = await _seed(2, connected=False)
        try:
            async with AsyncSessionLocal() as db:
                camp = Campaign(advertiser_id=user_id, name="Promo vieja", type="promo", message_text="Hola",
                                status="draft", ab_test={"enabled": False, "campaign_mode": "regular"})
                db.add(camp)
                await db.commit()
                cid = camp.id
            delay = MagicMock()
            with patch(DELAY, delay):
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    summary, args, error = await cs._preview_launch_campaign(db, user, {"campaign_id": str(cid)})
                    assert error is None and "gratis por web" in summary and "2 contacto(s)" in summary
                    data, error = await cs._execute_launch_campaign(db, user, args)
            assert error is None and data["web_only"] is True and data["recipients"] == 2
            async with AsyncSessionLocal() as db:
                c = await db.get(Campaign, cid)
            assert c.status == "running" and c.ab_test.get("web_only") is True
            delay.assert_called_once_with(str(cid))
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso10_con_chip_respeta_si_ya_era_solo_por_web(self):
        user_id, _ = await _seed(2, connected=True)
        try:
            async with AsyncSessionLocal() as db:
                camp = Campaign(advertiser_id=user_id, name="Promo vieja", type="promo", message_text="Hola",
                                status="paused", ab_test={"enabled": False, "campaign_mode": "regular", "web_only": True})
                db.add(camp)
                await db.commit()
                cid = camp.id
            with patch(DELAY, MagicMock()):
                async with AsyncSessionLocal() as db:
                    data, error = await cs._execute_launch_campaign(db, await db.get(User, user_id), {"campaign_id": str(cid)})
            assert error is None and data["web_only"] is True
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso10_conectar_el_chip_despues_de_la_vista_previa_no_cambia_a_whatsapp(self):
        user_id, _ = await _seed(2, connected=False)
        try:
            async with AsyncSessionLocal() as db:
                camp = Campaign(advertiser_id=user_id, name="Promo", type="promo", message_text="Hola",
                                status="draft", ab_test={"enabled": False, "campaign_mode": "regular"})
                db.add(camp)
                await db.commit()
                cid = camp.id
            async with AsyncSessionLocal() as db:
                _, args, _ = await cs._preview_launch_campaign(db, await db.get(User, user_id), {"campaign_id": str(cid)})
            assert args["web_only"] is True
            async with AsyncSessionLocal() as db:
                u = await db.get(User, user_id)
                u.meta_connection_status, u.meta_phone_number_id = "connected", "123"
                u.meta_token_cipher, u.meta_token_iv, u.meta_token_tag = "c", "i", "t"
                await db.commit()
            with patch(DELAY, MagicMock()):
                async with AsyncSessionLocal() as db:
                    data, _ = await cs._execute_launch_campaign(db, await db.get(User, user_id), args)
            assert data["web_only"] is True
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso10_con_chip_lanza_normal(self):
        user_id, _ = await _seed(2, connected=True)
        try:
            async with AsyncSessionLocal() as db:
                camp = Campaign(advertiser_id=user_id, name="Promo vieja", type="promo", message_text="Hola",
                                status="draft", ab_test={"enabled": False, "campaign_mode": "regular"})
                db.add(camp)
                await db.commit()
                cid = camp.id
            with patch(DELAY, MagicMock()):
                async with AsyncSessionLocal() as db:
                    data, error = await cs._execute_launch_campaign(db, await db.get(User, user_id), {"campaign_id": str(cid)})
            assert error is None and data["web_only"] is False
            async with AsyncSessionLocal() as db:
                assert "web_only" not in (await db.get(Campaign, cid)).ab_test
        finally:
            await _cleanup(user_id)


class TestSharedValidation:
    @pytest.mark.asyncio
    async def test_caso11_rest_y_copiloto_usan_la_misma_regla(self):
        from app.api.v1.campaigns import create_campaign
        from app.schemas.campaign import CampaignCreate
        user_id, _ = await _seed(1, subscription_status="churned")
        try:
            req = Request({"type": "http", "method": "POST", "path": "/api/v1/campaigns", "headers": [],
                           "client": ("t", 1), "query_string": b""})
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc:
                    await create_campaign(req, CampaignCreate(name="x", type="promo", message_text="y"),
                                          db=db, current_user=user, _=None, redis=None)
                _, _, copilot_error = await promo.preview(db, user, {"what": "x"})
            assert exc.value.status_code == 402 and exc.value.detail == copilot_error
        finally:
            await _cleanup(user_id)


class TestWhatsAppGuard:
    def test_caso4_whatsapp_solo_si_el_dueno_lo_nombro(self):
        assert promo.keep_asked_whatsapp({"whatsapp": True}, ["manda una promo de fundas"])["whatsapp"] is False
        for said in ("mándala por WhatsApp", "por wats", "por guasap también"):
            assert promo.keep_asked_whatsapp({"whatsapp": True}, [said])["whatsapp"] is True


class TestDiscountGuard:
    def test_caso5_2x1_no_es_descuento(self):
        # Pasó con la IA real (2026-10-28): "promo de 2x1" salió con discount_percent=2.
        args = {"what": "2x1 en fundas", "discount_percent": 2}
        assert promo.keep_asked_discount(args, ["manda una promo de 2x1 en fundas"])["discount_percent"] is None

    def test_caso5_el_porcentaje_que_si_dijo_se_queda(self):
        for said in ("con 15% de descuento", "15 por ciento", "un descuento de 15", "15 de descuento"):
            assert promo.keep_asked_discount({"discount_percent": 15}, [said])["discount_percent"] == 15

    def test_caso7_al_cambiar_se_conserva_el_descuento_pedido_antes(self):
        said = ["promo de micas con 10%", "hazla más corta"]
        assert promo.keep_asked_discount({"discount_percent": 10}, said)["discount_percent"] == 10

    @pytest.mark.asyncio
    async def test_caso5_el_copiloto_quita_el_descuento_inventado(self):
        user_id, _ = await _seed(1)
        try:
            call = llm_client.ToolCall("t1", "send_promo", {"what": "2x1 en fundas", "discount_percent": 2})
            reply = llm_client.ToolReply("", [call], [{"type": "tool_use", "id": "t1", "name": "send_promo", "input": call.input}])
            with patch.object(llm_client, "tool_completion", AsyncMock(return_value=reply)), \
                 patch(GEN, AsyncMock(return_value=[TEXT])), patch.object(cs, "get_redis_optional", AsyncMock(return_value=None)):
                async with AsyncSessionLocal() as db:
                    out = await cs.handle_chat(db, await db.get(User, user_id), "manda una promo de 2x1 en fundas", [])
            assert out["pending_confirmation"]["args"]["discount_percent"] == 0
            assert "cupón" not in out["reply"]
        finally:
            await _cleanup(user_id)


class TestCouponTheCustomerHears:
    def test_cupon_de_campana_sin_valor_no_dice_cero_por_ciento(self):
        from app.models.coupon import Coupon
        from app.services.customer_agent import _discount
        old = Coupon(code="A", description="15% de descuento", discount_type="percentage", discount_value=Decimal(0))
        assert _discount(old) == "15% de descuento"
        blank = Coupon(code="B", description=None, discount_type="percentage", discount_value=Decimal(0))
        assert "0%" not in _discount(blank)
        assert _discount(Coupon(code="C", discount_type="percentage", discount_value=Decimal(15))) == "15% de descuento"
        assert _discount(Coupon(code="D", discount_type="fixed", discount_value=Decimal(50))) == "$50 de descuento"
        assert _discount(Coupon(code="E", description="Premio: corte gratis", discount_type="free_item",
                                discount_value=Decimal(0))) == "Premio: corte gratis"

    def test_coupon_percent_solo_si_es_valido(self):
        from app.workers.task_helpers.campaign_ops import coupon_percent
        assert coupon_percent({"coupon_percent": 15}) == 15
        assert coupon_percent({}) == 0
        assert coupon_percent({"coupon_percent": "x"}) == 0
        assert coupon_percent({"coupon_percent": 500}) == 0
