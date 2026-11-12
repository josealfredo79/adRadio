"""La campaña que pregunta (docs/specs/2026-10-29-campana-que-pregunta.md).
Base y Redis reales; la IA, la voz, la subida de archivos y WhatsApp son falsos."""
import io
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image
from sqlalchemy import delete, select

from app.config import settings
from app.database import AsyncSessionLocal
from app.domain import campaign_builder as cb
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.product import Product
from app.models.sale import Sale
from app.models.user import User
from app.services import campaign_quota
from app.services.banner_service import BannerCopy, OfferCopy
from tests.test_campaign_quick import _sale
from tests.test_web_push import (  # noqa: F401 — _keys es fixture autouse
    _add_subs,
    _cleanup,
    _keys,
    _seed,
)

VARIANTS = ["📱 2x1 en micas este viernes en CityCell. Pídelo aquí.", "Otra versión de micas", "Tercera"]
AUDIO = "https://cdn.test/cuna.ogg"
PHOTO = f"{settings.BASE_URL}/api/v1/radio/audio/products/mica.jpg"
DELAY = "app.workers.tasks.schedule_campaign.delay"


def _mine(user_id) -> str:
    """Una foto que ese dueño subió (products/<su id>/…)."""
    return f"{settings.BASE_URL}/api/v1/radio/audio/products/{user_id}/foto.jpg"


def _jpeg() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (40, 120, 200)).save(buf, format="JPEG")
    return buf.getvalue()


@pytest.fixture(autouse=True)
def ai(monkeypatch):
    """La IA, la voz y el almacenamiento, falsos (cuestan o salen a internet)."""
    monkeypatch.setattr(campaign_quota, "COUNT_FROM", datetime(2020, 1, 1, tzinfo=timezone.utc))
    mocks = {
        "variants": AsyncMock(return_value=VARIANTS),
        "script": AsyncMock(return_value="¿Sabías que una mica salva tu pantalla? Te lo trae CityCell."),
        "audio": AsyncMock(return_value=AUDIO),
        "upload": AsyncMock(side_effect=lambda content, key, ctype: f"https://cdn.test/{key}"),
        "read": AsyncMock(return_value=_jpeg()),
        "copy": AsyncMock(return_value=BannerCopy(headline="2x1 en micas", subheadline="Este viernes",
                                                  cta="Pídelo", business_name="CityCell")),
        "offer": AsyncMock(return_value=OfferCopy(product="Micas", price="", when="Este viernes",
                                                  price_note="2x1", cta="Pídelo", business_name="CityCell")),
        "later": MagicMock(return_value=None),
    }
    with patch("app.services.claude_service.generate_campaign_variants", mocks["variants"]), \
         patch("app.services.radio_service.generate_radio_script", mocks["script"]), \
         patch("app.services.radio_service.generate_radio_ad", mocks["audio"]), \
         patch("app.services.storage_service.upload_bytes", mocks["upload"]), \
         patch("app.services.storage_service.read_bytes", mocks["read"]), \
         patch("app.services.banner_service.generate_banner_copy_with_claude", mocks["copy"]), \
         patch("app.services.banner_service.generate_offer_copy", mocks["offer"]), \
         patch("app.services.messaging_throttle.send_starts_label", mocks["later"]):
        yield mocks


async def _owner(n_contacts=1, plan="growth", photo=False):
    user_id, contacts = await _seed(n_contacts)
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        user.current_plan, user.subscription_status, user.business_name = plan, "active", "CityCell"
        if photo:
            db.add(Product(advertiser_id=user_id, name="Mica templada", price=Decimal(80),
                           photo_url=PHOTO))
        await db.commit()
    return user_id, contacts


async def _turn(user_id, campaign_id=None, choice=None, text=None, prefill=None):
    async with AsyncSessionLocal() as db:
        user = await db.get(User, user_id)
        return await cb.handle(db, user, campaign_id, choice, text, prefill)


async def _camp(campaign_id) -> Campaign:
    async with AsyncSessionLocal() as db:
        return await db.get(Campaign, uuid.UUID(campaign_id))


async def _clean(user_id):
    async with AsyncSessionLocal() as db:
        for model in (Product, Sale):
            await db.execute(delete(model).where(model.advertiser_id == user_id))
        await db.commit()
    await _cleanup(user_id)


def _ids(r):
    return [c["id"] for c in r["choices"]]


class TestCampanaQuePregunta:
    @pytest.mark.asyncio
    async def test_caso1_empieza_preguntando_que_anuncias(self):
        user_id, _ = await _owner()
        try:
            r = await _turn(user_id)
            assert (r["step"], r["text"], r["input"]) == ("what", "¿Qué quieres anunciar?", "what")
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso2_pregunta_como_con_el_mejor_primero(self):
        user_id, _ = await _owner()
        try:
            r = await _turn(user_id, text="2x1 en micas este viernes")
            assert r["text"] == "¿Cómo se lo mando?"
            assert _ids(r) == ["f:text", "f:photo", "f:audio"]  # sin fotos en el catálogo: texto primero
        finally:
            await _clean(user_id)
        user_id, _ = await _owner(photo=True)
        try:
            r = await _turn(user_id, text="2x1 en micas este viernes")
            assert _ids(r)[0] == "f:photo"  # hay foto de micas: foto primero
            r = await _turn(user_id, text="dato curioso de pantallas rotas")
            assert _ids(r)[0] == "f:audio"
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso3_audio_estilo_sugerido_y_la_cuna_para_escuchar(self, ai):
        user_id, _ = await _owner()
        try:
            r = await _turn(user_id, text="dato curioso de micas")
            r = await _turn(user_id, r["campaign_id"], "f:audio")
            assert r["step"] == "style" and _ids(r)[0] == "s:capsula" and len(_ids(r)) == 7
            r = await _turn(user_id, r["campaign_id"], "s:capsula")
            assert r["step"] == "preview" and r["preview"]["kind"] == "audio"
            assert r["preview"]["audio_url"] == AUDIO
            assert _ids(r) == ["ok", "other", "edit"]
            assert ai["script"].await_args.kwargs["mode"] == "capsula"
            camp = await _camp(r["campaign_id"])
            assert (camp.ab_test["campaign_mode"], camp.ab_test["audio_url"]) == ("capsula", AUDIO)
            # Cambiar el texto de la cuña la vuelve a grabar con ese guion.
            r = await _turn(user_id, r["campaign_id"], "edit")
            r = await _turn(user_id, r["campaign_id"], text="Micas 2x1 en CityCell, ven hoy.")
            assert r["step"] == "preview" and ai["audio"].await_args.kwargs["_script"] == "Micas 2x1 en CityCell, ven hoy."
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso4_con_foto_ofrece_las_del_catalogo_y_pone_la_promo_encima(self, ai):
        user_id, _ = await _owner(photo=True)
        try:
            r = await _turn(user_id, text="2x1 en micas este viernes")
            r = await _turn(user_id, r["campaign_id"], "f:photo")
            assert r["step"] == "photo" and r["input"] == "photo"
            assert [c["label"] for c in r["choices"]] == ["Foto de Mica templada", "📷 Tomar otra foto", "Sin foto"]
            r = await _turn(user_id, r["campaign_id"], r["choices"][0]["id"])
            assert r["step"] == "preview" and r["preview"]["kind"] == "image"
            assert r["preview"]["image_url"].endswith(".jpg") and r["preview"]["text"] == VARIANTS[0]
            ai["read"].assert_any_await(PHOTO)
            content = ai["upload"].await_args.args[0]
            assert Image.open(io.BytesIO(content)).size == (1080, 1080)  # su foto en el cartel de oferta
            camp = await _camp(r["campaign_id"])
            assert camp.ab_test["photo_fixed"] is True and camp.ab_test["campaign_mode"] == "banner"
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso4_solo_abre_fotos_guardadas_por_iaradio(self, ai):
        user_id, _ = await _owner()
        try:
            r = await _turn(user_id, text="2x1 en micas")
            r = await _turn(user_id, r["campaign_id"], "f:photo")
            r = await _turn(user_id, r["campaign_id"], "upload", text="http://169.254.169.254/latest/meta-data")
            assert r["step"] == "photo" and r["text"].startswith("No pude abrir esa foto")
            ai["read"].assert_not_awaited()
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso5_texto_con_catalogo_y_otra_version(self):
        user_id, _ = await _owner()
        try:
            r = await _turn(user_id, text="2x1 en micas este viernes")
            r = await _turn(user_id, r["campaign_id"], "f:text")
            assert r["preview"] == {"kind": "text", "text": VARIANTS[0], "image_url": None, "audio_url": None}
            r = await _turn(user_id, r["campaign_id"], "other")
            assert r["preview"]["text"] == VARIANTS[1]
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso6_a_quien_y_uno_por_nombre(self):
        user_id, (cid,) = await _owner()
        try:
            r = await _turn(user_id, text="2x1 en micas")
            r = await _turn(user_id, r["campaign_id"], "f:text")
            r = await _turn(user_id, r["campaign_id"], "ok")
            assert r["step"] == "audience" and _ids(r) == ["a:all", "a:bought", "a:one"]
            r = await _turn(user_id, r["campaign_id"], "a:one")
            assert r["step"] == "contact" and r["input"] == "contact"
            r = await _turn(user_id, r["campaign_id"], text="nadie así")
            assert r["text"].startswith("No encontré a «nadie así»")
            r = await _turn(user_id, r["campaign_id"], text="Cliente 0")
            assert _ids(r) == [f"c:{cid}"]
            r = await _turn(user_id, r["campaign_id"], f"c:{cid}")
            assert r["step"] == "send"
            assert (await _camp(r["campaign_id"])).segment == {"specific_contacts": [str(cid)]}
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso7_cupon_solo_si_el_texto_promete_descuento(self):
        user_id, _ = await _owner()
        try:
            r = await _turn(user_id, text="10% en cargadores este fin de semana")
            r = await _turn(user_id, r["campaign_id"], "f:text")
            r = await _turn(user_id, r["campaign_id"], "ok")
            r = await _turn(user_id, r["campaign_id"], "a:all")
            assert r["step"] == "discount" and _ids(r) == ["d:10", "d:0"]
            r = await _turn(user_id, r["campaign_id"], "d:10")
            assert r["step"] == "send"
            assert (await _camp(r["campaign_id"])).ab_test["coupon_percent"] == 10

            r = await _turn(user_id, choice="new")
            r = await _turn(user_id, text="2x1 en micas")
            r = await _turn(user_id, r["campaign_id"], "f:text")
            r = await _turn(user_id, r["campaign_id"], "ok")
            r = await _turn(user_id, r["campaign_id"], "a:all")
            assert r["step"] == "send"  # 2x1: sin pregunta de cupón
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso8_alcance_mandar_gratis_por_web_y_de_noche(self, ai):
        user_id, (cid,) = await _owner()
        try:
            await _add_subs(user_id, cid, 1)
            r = await _turn(user_id, text="2x1 en micas")
            r = await _turn(user_id, r["campaign_id"], "f:text")
            r = await _turn(user_id, r["campaign_id"], "ok")
            ai["later"].return_value = "mañana a las 8:00 a. m."
            r = await _turn(user_id, r["campaign_id"], "a:all")
            assert r["text"].startswith("Le llega: a 1 cliente le suena aviso")
            assert "Es de noche: sale mañana a las 8:00 a. m." in r["text"]
            assert _ids(r) == ["web"]  # sin chip: no se ofrece WhatsApp
            delay = MagicMock()
            with patch(DELAY, delay):
                r = await _turn(user_id, r["campaign_id"], "web")
            assert r["done"] and r["text"] == "¡Listo! Tu promo va gratis por web. Sale mañana a las 8:00 a. m."
            camp = await _camp(r["campaign_id"])
            assert camp.status == "running" and camp.ab_test["web_only"] is True
            delay.assert_called_once_with(r["campaign_id"])
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso9_si_lo_dice_todo_salta_a_la_vista_previa_y_a_mandar(self, ai):
        user_id, (cid,) = await _owner()
        try:
            await _sale(user_id, cid, days_ago=3)
            r = await _turn(user_id, text="manda un audio de dato curioso de 2x1 en micas a los que compraron")
            assert r["step"] == "preview" and r["preview"]["kind"] == "audio"
            assert ai["script"].await_args.kwargs["mode"] == "capsula"
            r = await _turn(user_id, r["campaign_id"], "ok")
            assert r["step"] == "send"
            assert (await _camp(r["campaign_id"])).segment == {"bought_days": 90}
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso10_arranque_sin_prueba_ve_candado_y_no_gasta(self, ai):
        user_id, _ = await _owner(plan="starter")
        try:
            async with AsyncSessionLocal() as db:
                db.add(Campaign(advertiser_id=user_id, name="Cuña vieja", type="promo", status="completed",
                                message_text="x", segment={}, ab_test={"campaign_mode": "radio", "audio_url": AUDIO}))
                await db.commit()
            r = await _turn(user_id, text="2x1 en micas")
            audio = next(c for c in r["choices"] if c["id"] == "f:audio")
            assert audio == {"id": "f:audio", "label": "🔒 Audio de radio", "locked": True}
            r = await _turn(user_id, r["campaign_id"], "f:audio")
            assert r["step"] == "format" and "audio de prueba" in r["text"]
            ai["audio"].assert_not_awaited()
            # Si lo pidió de una vez, también lo explica y pregunta el formato.
            r = await _turn(user_id, text="manda un audio de 2x1 en micas")
            assert r["step"] == "format" and "audio de prueba" in r["text"]
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso11_a_medias_queda_borrador_y_se_retoma(self):
        user_id, _ = await _owner()
        try:
            r = await _turn(user_id, text="2x1 en micas")
            cid = r["campaign_id"]
            r = await _turn(user_id, cid, "f:text")
            r = await _turn(user_id)
            assert r["step"] == "resume" and r["text"] == "¿Seguimos con tu promo «2x1 en micas»?"
            assert _ids(r) == [f"resume:{cid}", "new"]
            r = await _turn(user_id, choice=f"resume:{cid}")
            assert r["step"] == "preview" and r["campaign_id"] == cid
            r = await _turn(user_id, choice="new")
            assert r["step"] == "what"
            assert (await _camp(cid)).status == "draft"
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso13_la_foto_que_vio_es_la_que_se_manda_por_whatsapp(self, ai):
        from app.workers.task_helpers import campaign_ops

        user_id, (cid,) = await _owner(photo=True)
        try:
            r = await _turn(user_id, text="2x1 en micas")
            r = await _turn(user_id, r["campaign_id"], "f:photo")
            r = await _turn(user_id, r["campaign_id"], r["choices"][0]["id"])
            camp = await _camp(r["campaign_id"])
            image = camp.image_url
            send = MagicMock()
            async with AsyncSessionLocal() as db:
                camp = await db.get(Campaign, camp.id)
                # Lo que deja start_campaign al tocar "También por WhatsApp".
                camp.ab_test = {k: v for k, v in camp.ab_test.items() if k != "web_only"}
                user = await db.get(User, user_id)
                user.messages_remaining = 10
                contact = await db.get(Contact, cid)
                with patch.object(campaign_ops, "_offer_or_queue", AsyncMock(return_value=("open", None))), \
                     patch("app.services.banner_service.generate_banner_png", side_effect=AssertionError("no redibuja")), \
                     patch("app.workers.tasks.send_whatsapp_image_message.apply_async", send):
                    await campaign_ops.send_banner_messages(db, camp, [contact], user, camp.ab_test, ban_delay=0)
            send.assert_called_once()
            assert send.call_args.kwargs["args"][2] == image
            assert send.call_args.kwargs["args"][3].startswith(VARIANTS[0])
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso12_en_el_copiloto_web_abre_la_misma_platica(self):
        from app.services import copilot_service as cs
        from app.services import llm_client

        user_id, _ = await _owner()
        try:
            args = {"what": "10% en cargadores", "format": "text"}
            call = llm_client.ToolCall("t1", "build_campaign", args)
            reply = llm_client.ToolReply("", [call], [{"type": "tool_use", "id": "t1", "name": "build_campaign", "input": args}])
            completion = AsyncMock(return_value=reply)
            with patch.object(llm_client, "tool_completion", completion), \
                 patch.object(cs, "get_redis_optional", AsyncMock(return_value=None)):
                async with AsyncSessionLocal() as db:
                    out = await cs.handle_chat(db, await db.get(User, user_id), "haz una campaña de 10% en cargadores", [])
            (action,) = out["actions"]
            step = action["data"]["builder"]
            # La IA puso format="text" pero el dueño no lo dijo: se le pregunta (keep_said).
            assert action["tool"] == "build_campaign" and step["step"] == "format"
            assert (await _camp(step["campaign_id"])).name == "10% en cargadores"
            assert out["reply"] == step["text"] and out["pending_confirmation"] is None
            completion.assert_awaited_once()  # los botones siguen solos, sin otra vuelta del modelo
            tools = [t["name"] for t in completion.await_args.kwargs["tools"]]
            assert "build_campaign" in tools and "send_promo" not in tools
            # En WhatsApp escrito ahora también abre la plática (Fase C); por voz
            # sigue la promo rápida de send_promo.
            assert "build_campaign" in [t["name"] for t in cs._tools_for("whatsapp")]
            assert "send_promo" not in [t["name"] for t in cs._tools_for("whatsapp")]
            assert "send_promo" in [t["name"] for t in cs._tools_for("voz")]
            assert "build_campaign" not in [t["name"] for t in cs._tools_for("voz")]
        finally:
            await _clean(user_id)


def test_del_copiloto_solo_se_queda_lo_que_dijo_el_dueno():
    # IA real (Gemini, 2026-10-29): ponía format="text" sin que el dueño lo dijera.
    assert cb.keep_said({"what": "2x1 en micas", "format": "text"}, ["haz una campaña de 2x1 en micas"]) == {"what": "2x1 en micas"}
    assert cb.keep_said({"what": "dato curioso de micas", "format": "audio", "style": "capsula", "audience": "bought"},
                        ["manda un audio de dato curioso de micas a los que me compraron"]) == {
        "what": "dato curioso de micas", "format": "audio", "style": "capsula", "audience": "bought"}
    assert cb.keep_said({"what": "fundas", "audience": "one", "contact": "Lupe"}, ["mándale a Lupe una promo de fundas"])["contact"] == "Lupe"


class TestLoQueVioRevisorDinero:
    @pytest.mark.asyncio
    async def test_mandar_dos_veces_sale_una_sola_vez(self):
        import asyncio as aio

        user_id, _ = await _owner()
        try:
            r = await _turn(user_id, text="2x1 en micas")
            r = await _turn(user_id, r["campaign_id"], "f:text")
            r = await _turn(user_id, r["campaign_id"], "ok")
            r = await _turn(user_id, r["campaign_id"], "a:all")
            delay = MagicMock()
            with patch(DELAY, delay):
                first, second = await aio.gather(_turn(user_id, r["campaign_id"], "web"),
                                                 _turn(user_id, r["campaign_id"], "web"))
            delay.assert_called_once()
            assert {first["text"], second["text"]} == {"¡Listo! Tu promo va gratis por web.", "Esta promo ya se mandó."}
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_estilo_formato_o_cupon_inventados_no_pasan(self, ai):
        user_id, _ = await _owner()
        try:
            r = await _turn(user_id, text="2x1 en micas")
            r = await _turn(user_id, r["campaign_id"], "f:video")
            assert r["step"] == "format"
            r = await _turn(user_id, r["campaign_id"], "f:audio")
            r = await _turn(user_id, r["campaign_id"], "s:xyz")
            assert r["step"] == "style"
            ai["audio"].assert_not_awaited()
            r = await _turn(user_id, choice="new")
            r = await _turn(user_id, text="10% en cargadores")
            r = await _turn(user_id, r["campaign_id"], "f:text")
            r = await _turn(user_id, r["campaign_id"], "ok")
            r = await _turn(user_id, r["campaign_id"], "a:all")
            for bad in ("d:100", "d:-5", "d:abc"):
                r = await _turn(user_id, r["campaign_id"], bad)
                assert r["step"] == "discount"
            assert "has_coupon" not in (await _camp(r["campaign_id"])).ab_test
        finally:
            await _clean(user_id)


class TestPruebasFinales:
    """Lo que faltaba probar de la plática: los caminos que no son el feliz
    (sin clientes, sin foto, con candado, por WhatsApp) y que nadie más pueda
    seguir el borrador de otro dueño."""

    @pytest.mark.asyncio
    async def test_caso4_cartel_de_colores_cuando_no_hay_foto(self, ai):
        user_id, _ = await _owner()
        try:
            r = await _turn(user_id, text="2x1 en micas")
            r = await _turn(user_id, r["campaign_id"], "f:photo")
            assert [c["label"] for c in r["choices"]] == ["📷 Tomar foto", "Sin foto"]
            assert "¿Le tomas una foto?" in r["text"]
            r = await _turn(user_id, r["campaign_id"], "poster")
            assert r["step"] == "preview" and r["preview"]["kind"] == "image"
            assert r["preview"]["image_url"].endswith(".jpg")
            ai["read"].assert_not_awaited()  # el cartel se dibuja en el servidor
            assert ai["upload"].await_args.args[0].startswith(b"\xff\xd8\xff")
            camp = await _camp(r["campaign_id"])
            assert camp.ab_test["photo_fixed"] is True and camp.ab_test["campaign_mode"] == "banner"
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso4_tambien_puede_subir_su_propia_foto(self, ai):
        user_id, _ = await _owner()
        try:
            r = await _turn(user_id, text="2x1 en micas")
            r = await _turn(user_id, r["campaign_id"], "f:photo")
            mine = _mine(user_id)
            r = await _turn(user_id, r["campaign_id"], "upload", text=mine)
            assert r["step"] == "preview" and r["preview"]["kind"] == "image"
            assert r["preview"]["text"] == VARIANTS[0]
            ai["read"].assert_awaited_with(mine)
            content = ai["upload"].await_args.args[0]
            assert Image.open(io.BytesIO(content)).size == (1080, 1080)
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso7_cien_por_ciento_no_se_lee_como_cero(self):
        # Venía de la promo de 3 toques: "100%" se leía como 0 y avisaba
        # "Tu mensaje dice 0%". La plática no debe ofrecer un cupón de 100%.
        user_id, _ = await _owner()
        try:
            r = await _turn(user_id, text="100% garantizado en micas")
            r = await _turn(user_id, r["campaign_id"], "f:text")
            r = await _turn(user_id, r["campaign_id"], "ok")
            r = await _turn(user_id, r["campaign_id"], "a:all")
            assert r["step"] == "discount"
            assert _ids(r) == ["d:10", "d:15", "d:20", "d:0"]
            assert "100" not in r["text"] and "0%" not in r["text"]
            r = await _turn(user_id, r["campaign_id"], "d:10")
            assert (await _camp(r["campaign_id"])).ab_test["coupon_percent"] == 10
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso8_sin_clientes_regresa_a_la_audiencia(self):
        user_id, _ = await _owner(n_contacts=0)
        try:
            r = await _turn(user_id, text="2x1 en micas")
            r = await _turn(user_id, r["campaign_id"], "f:text")
            r = await _turn(user_id, r["campaign_id"], "ok")
            r = await _turn(user_id, r["campaign_id"], "a:all")
            assert r["step"] == "audience" and _ids(r) == ["a:all", "a:bought", "a:one"]
            assert "Todavía no tienes clientes a quién mandarla." in r["text"]
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso8_tambien_por_whatsapp_manda_por_los_dos(self, ai):
        user_id, _ = await _owner()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                user.meta_connection_status = "connected"
                user.meta_phone_number_id = "123456"
                user.meta_token_cipher = "cifrado"
                user.meta_token_iv = "iv"
                user.meta_token_tag = "tag"
                user.messages_remaining = 10
                await db.commit()
            r = await _turn(user_id, text="2x1 en micas")
            r = await _turn(user_id, r["campaign_id"], "f:text")
            r = await _turn(user_id, r["campaign_id"], "ok")
            r = await _turn(user_id, r["campaign_id"], "a:all")
            assert r["step"] == "send" and _ids(r) == ["web", "whatsapp"]
            assert "También por WhatsApp (aprox $" in r["choices"][1]["label"]
            delay = MagicMock()
            with patch(DELAY, delay):
                r = await _turn(user_id, r["campaign_id"], "whatsapp")
            assert r["done"] and r["text"] == "¡Listo! Tu promo va por web y WhatsApp."
            camp = await _camp(r["campaign_id"])
            assert camp.status == "running" and camp.ab_test.get("web_only") is not True
            delay.assert_called_once_with(r["campaign_id"])
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso10_arranque_sin_prueba_de_imagen_ve_candado(self, ai):
        user_id, _ = await _owner(plan="starter")
        try:
            async with AsyncSessionLocal() as db:
                db.add(Campaign(advertiser_id=user_id, name="Cartel viejo", type="promo", status="completed",
                                message_text="x", segment={}, ab_test={"campaign_mode": "banner"}))
                await db.commit()
            r = await _turn(user_id, text="2x1 en micas")
            photo = next(c for c in r["choices"] if c["id"] == "f:photo")
            assert photo == {"id": "f:photo", "label": "🔒 Con foto", "locked": True}
            r = await _turn(user_id, r["campaign_id"], "f:photo")
            assert r["step"] == "format" and "imagen de prueba" in r["text"]
            ai["upload"].assert_not_awaited()
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso11_borrador_de_hace_mas_de_una_semana_no_se_retoma(self):
        user_id, _ = await _owner()
        try:
            r = await _turn(user_id, text="2x1 en micas")
            cid = r["campaign_id"]
            await _turn(user_id, cid, "f:text")
            async with AsyncSessionLocal() as db:
                camp = await db.get(Campaign, uuid.UUID(cid))
                camp.created_at = datetime.now(timezone.utc) - timedelta(days=8)
                await db.commit()
            r = await _turn(user_id)
            assert (r["step"], r["text"], r["input"]) == ("what", "¿Qué quieres anunciar?", "what")
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_otro_dueno_no_puede_seguir_este_borrador(self):
        user_id, _ = await _owner()
        other_id, _ = await _owner()
        try:
            r = await _turn(user_id, text="2x1 en micas")
            r = await _turn(other_id, campaign_id=r["campaign_id"], choice="f:text")
            assert (r["campaign_id"], r["step"], r["input"]) == (None, "what", "what")
            assert r["text"] == "Esa campaña ya no existe. ¿Qué quieres anunciar?"
        finally:
            await _clean(user_id)
            await _clean(other_id)

    @pytest.mark.asyncio
    async def test_el_endpoint_del_panel_abre_y_contesta_la_platica(self):
        from httpx import ASGITransport, AsyncClient

        from app.api.deps import get_current_user
        from app.main import app

        user_id, _ = await _owner()

        async def _current_user():
            async with AsyncSessionLocal() as db:
                return await db.get(User, user_id)

        app.dependency_overrides[get_current_user] = _current_user
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                r = await client.post("/api/v1/campaigns/builder", json={"text": "2x1 en micas"})
                assert r.status_code == 200
                body = r.json()
                assert body["step"] == "format" and body["campaign_id"]
                r = await client.post("/api/v1/campaigns/builder",
                                      json={"campaign_id": body["campaign_id"], "choice": "f:text"})
                assert r.status_code == 200 and r.json()["step"] == "preview"
        finally:
            app.dependency_overrides.clear()
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_el_endpoint_sin_sesion_no_abre_nada(self):
        from httpx import ASGITransport, AsyncClient

        from app.main import app

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            r = await client.post("/api/v1/campaigns/builder", json={"text": "2x1 en micas"})
        assert r.status_code == 401


class TestCartelDeOferta:
    """El cartel de oferta toma del negocio lo que la IA no puede inventar:
    foto y precio normal del catálogo, logo, contacto y la fecha concreta."""

    @pytest.mark.asyncio
    async def test_precio_de_antes_y_foto_salen_del_catalogo(self, ai):
        user_id, _ = await _owner(photo=True)  # Mica templada $80 con foto
        ai["offer"].return_value = OfferCopy(product="Mica templada", price="$60", when="Solo mañana")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                mica = (await db.execute(select(Product).where(Product.advertiser_id == user_id))).scalar_one()
                offer, photo, logo = await cb._offer_details(db, user, "mica templada a $60 solo mañana", f"p:{mica.id}")
            assert offer.old_price == "$80" and offer.price == "$60"
            assert photo is not None and logo is None
            assert offer.when != "Solo mañana" and offer.when.lower().startswith(("solo hoy · ", "solo el "))
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_precio_del_catalogo_menor_no_se_pone_como_antes(self, ai):
        user_id, _ = await _owner(photo=True)  # $80
        ai["offer"].return_value = OfferCopy(product="Mica templada", price="$90")
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                offer, _, _ = await cb._offer_details(db, user, "mica templada a $90")
            assert offer.old_price == ""
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_dos_productos_igual_de_parecidos_no_se_escoge_ninguno(self, ai):
        user_id, _ = await _owner()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Product(advertiser_id=user_id, name="Cargador Samsung", price=Decimal(150)))
                db.add(Product(advertiser_id=user_id, name="Cargador Xiaomi", price=Decimal(200)))
                await db.commit()
                user = await db.get(User, user_id)
                assert await cb._offer_product(db, user, "cargador a $100") is None
                assert (await cb._offer_product(db, user, "cargador xiaomi a $100")).name == "Cargador Xiaomi"
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_nombre_corto_encuentra_el_unico_producto(self, ai):
        """"cargador a $99" es el "Cargador marca" de CityCell (prueba real 12-nov)."""
        user_id, _ = await _owner()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Product(advertiser_id=user_id, name="Cargador marca", price=Decimal(120)))
                db.add(Product(advertiser_id=user_id, name="Funda para Samsung", price=Decimal(200)))
                await db.commit()
                user = await db.get(User, user_id)
                for said in ("Promo: cargador a $99, solo hoy", "cargadores a 99 hasta el domingo 15",
                             "Cargador marca a $99 mañana"):
                    assert (await cb._offer_product(db, user, said)).name == "Cargador marca", said
                # Lo que dice de más no está en ese nombre: no es ese producto.
                assert await cb._offer_product(db, user, "cargador samsung a $99") is None
                assert await cb._offer_product(db, user, "samsung a $99") is None
                assert await cb._offer_product(db, user, "quiero sacar una promo a $99") is None
                # La foto tomada solo se guarda con el nombre completo.
                assert await cb._offer_product(db, user, "cargador a $99", short=False) is None
        finally:
            await _clean(user_id)

    def test_telefono_del_cartel(self):
        from types import SimpleNamespace as N
        meta = {"meta_display_phone_number": "+52 1 953 172 4341", "whatsapp_number": "9539999999"}
        assert cb._poster_contact(N(meta_connection_status="connected", phone="9530000000", **meta)) \
            == "WhatsApp 953 172 4341"
        # WhatsApp desconectado: el número de Meta ya no contesta; va el de su perfil.
        assert cb._poster_contact(N(meta_connection_status="not_connected", phone="+529531112233", **meta)) \
            == "Tel. 953 111 2233"
        # El número personal de avisos (whatsapp_number) nunca sale en el cartel.
        assert cb._poster_contact(N(meta_connection_status="not_connected", phone=None, **meta)) == ""

    def test_dia_de_envio_de_noche_es_manana(self):
        tz = timezone(timedelta(hours=-6))
        today, send = cb._send_day(datetime(2026, 11, 11, 22, 30, tzinfo=tz))  # miércoles noche
        assert (today.day, send.day) == (11, 12)
        today, send = cb._send_day(datetime(2026, 11, 11, 12, 0, tzinfo=tz))
        assert today == send

    @pytest.mark.asyncio
    async def test_palabras_comunes_no_escogen_otro_producto(self, ai):
        """"cargador para samsung" no es la "Funda para Samsung" (foto y Antes falsos)."""
        user_id, _ = await _owner()
        try:
            async with AsyncSessionLocal() as db:
                db.add(Product(advertiser_id=user_id, name="Funda para Samsung", price=Decimal(200)))
                db.add(Product(advertiser_id=user_id, name="Cargador tipo C", price=Decimal(250)))
                db.add(Product(advertiser_id=user_id, name="Pantalla iPhone 11", price=Decimal(1200)))
                await db.commit()
                user = await db.get(User, user_id)
                assert await cb._offer_product(db, user, "cargador para samsung a $150") is None
                assert await cb._offer_product(db, user, "Reparación de pantalla a $500") is None
                assert (await cb._offer_product(db, user, "cargadores tipo c a $150")).name == "Cargador tipo C"
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_logo_ilegible_no_tumba_el_cartel(self, ai, monkeypatch):
        user_id, _ = await _owner(photo=True)
        ai["offer"].return_value = OfferCopy(product="Mica templada", price="$60")

        async def boom(url):
            raise OSError("no está")

        monkeypatch.setattr("app.services.storage_service.read_bytes", boom)
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                user.logo_url = PHOTO
                offer, photo, logo = await cb._offer_details(db, user, "mica templada a $60")
            assert offer.old_price == "$80" and photo is None and logo is None
        finally:
            await _clean(user_id)

    def test_de_madrugada_manana_es_el_mismo_dia(self):
        """"Solo mañana" a las 00:01 del jueves quiere decir el jueves."""
        from app.services.banner_service import concrete_when
        tz = timezone(timedelta(hours=-6))
        today, send = cb._send_day(datetime(2026, 11, 12, 0, 1, tzinfo=tz))
        assert (today.day, send.day) == (11, 12)
        assert concrete_when("Solo mañana", today, send) == "Solo hoy · jueves 12"
        # "Solo hoy" escrito de madrugada no se vuelve una fecha que ya pasó.
        assert concrete_when("Solo hoy", today, send) == "Solo hoy"


class TestCartelQueConvence:
    """docs/specs/2026-11-12-cartel-que-convence.md: el cartel lleva la foto del
    producto; si el Catálogo no la tiene, se le pide al dueño y se guarda."""

    @staticmethod
    async def _add(user_id, name, price, photo=None):
        async with AsyncSessionLocal() as db:
            p = Product(advertiser_id=user_id, name=name, price=Decimal(price), photo_url=photo)
            db.add(p)
            await db.commit()
            return p.id

    @staticmethod
    async def _to_photo(user_id, what):
        r = await _turn(user_id, text=what)
        return await _turn(user_id, r["campaign_id"], "f:photo")

    @pytest.mark.asyncio
    async def test_caso1_con_foto_en_el_catalogo_es_el_primer_boton(self, ai):
        user_id, _ = await _owner(photo=True)  # Mica templada $80 con foto
        try:
            r = await self._to_photo(user_id, "mica templada a $60 solo mañana")
            assert r["choices"][0]["label"] == "Foto de Mica templada"
            r = await _turn(user_id, r["campaign_id"], r["choices"][0]["id"])
            assert r["step"] == "preview" and r["preview"]["image_url"].endswith(".jpg")
            ai["read"].assert_any_await(PHOTO)
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso2_sin_foto_pide_tomarla_y_no_ofrece_fotos_de_otra_cosa(self, ai):
        user_id, _ = await _owner()
        await self._add(user_id, "Cargador marca", 120)  # sin foto
        await self._add(user_id, "Funda roja", 90, PHOTO)  # otra cosa, con foto
        try:
            r = await self._to_photo(user_id, "cargador marca a $100 solo mañana")
            assert r["step"] == "photo"
            assert "¿Le tomas una foto? Con la foto de «Cargador marca»" in r["text"]
            assert [c["label"] for c in r["choices"]] == ["📷 Tomar foto", "Sin foto"]
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso3_la_foto_tomada_se_guarda_en_el_catalogo(self, ai):
        user_id, _ = await _owner()
        pid = await self._add(user_id, "Cargador marca", 120)
        try:
            r = await self._to_photo(user_id, "cargador marca a $100 solo mañana")
            r = await _turn(user_id, r["campaign_id"], "upload", text=_mine(user_id))
            assert r["step"] == "preview"
            async with AsyncSessionLocal() as db:
                assert (await db.get(Product, pid)).photo_url == _mine(user_id)
            # La próxima promo de ese producto ya no la pide.
            r = await self._to_photo(user_id, "cargador marca a $90 este viernes")
            assert r["choices"][0]["label"] == "Foto de Cargador marca"
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso3_no_cambia_la_foto_que_ya_tenia(self, ai):
        user_id, _ = await _owner(photo=True)
        try:
            r = await self._to_photo(user_id, "mica templada a $60")
            r = await _turn(user_id, r["campaign_id"], "upload", text=_mine(user_id))
            async with AsyncSessionLocal() as db:
                mica = (await db.execute(select(Product).where(Product.advertiser_id == user_id))).scalar_one()
            assert mica.photo_url == PHOTO
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso4_si_no_esta_en_el_catalogo_no_se_crea(self, ai):
        user_id, _ = await _owner()
        try:
            r = await self._to_photo(user_id, "audífonos bluetooth a $250")
            r = await _turn(user_id, r["campaign_id"], "upload", text=_mine(user_id))
            assert r["step"] == "preview" and r["preview"]["kind"] == "image"
            async with AsyncSessionLocal() as db:
                rows = (await db.execute(select(Product).where(Product.advertiser_id == user_id))).scalars().all()
            assert rows == []
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso5_sin_foto_sale_el_cartel_de_letras(self, ai):
        user_id, _ = await _owner()
        try:
            r = await self._to_photo(user_id, "2x1 en micas")
            r = await _turn(user_id, r["campaign_id"], "poster")
            assert r["step"] == "preview" and r["preview"]["kind"] == "image"
            ai["read"].assert_not_awaited()
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso11_foto_de_otro_negocio_no_se_abre(self, ai):
        user_id, _ = await _owner()
        try:
            r = await self._to_photo(user_id, "2x1 en micas")
            other = f"{settings.BASE_URL}/api/v1/radio/audio/products/{uuid.uuid4()}/foto.jpg"
            r = await _turn(user_id, r["campaign_id"], "upload", text=other)
            assert r["step"] == "photo" and r["text"].startswith("No pude abrir esa foto")
            assert [c["label"] for c in r["choices"]] == ["📷 Tomar foto", "Sin foto"]
            ai["read"].assert_not_awaited()
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso2_palabras_de_relleno_no_ofrecen_otra_foto(self, ai):
        """"Mica para iPhone" no es la "Funda para Samsung" (solo comparten "para")."""
        user_id, _ = await _owner()
        await self._add(user_id, "Funda para Samsung", 200, PHOTO)
        try:
            r = await self._to_photo(user_id, "Mica para iPhone a $50")
            assert [c["label"] for c in r["choices"]] == ["📷 Tomar foto", "Sin foto"]
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso3_la_foto_se_guarda_segun_el_texto_del_dueno_no_de_la_ia(self, ai):
        user_id, _ = await _owner()
        fid = await self._add(user_id, "Funda Samsung", 200)  # sin foto
        ai["offer"].return_value = OfferCopy(product="Funda Samsung", price="$150")  # la IA se equivoca
        try:
            r = await self._to_photo(user_id, "cargador para samsung a $150")
            await _turn(user_id, r["campaign_id"], "upload", text=_mine(user_id))
            async with AsyncSessionLocal() as db:
                assert (await db.get(Product, fid)).photo_url is None
        finally:
            await _clean(user_id)

    @pytest.mark.asyncio
    async def test_caso11_direccion_disfrazada_de_otro_negocio_no_se_abre(self, ai):
        user_id, _ = await _owner()
        try:
            r = await self._to_photo(user_id, "2x1 en micas")
            fake = (f"{settings.BASE_URL}/api/v1/radio/audio/products/{uuid.uuid4()}/x.jpg"
                    f"?a=/products/{user_id}/")
            r = await _turn(user_id, r["campaign_id"], "upload", text=fake)
            assert r["step"] == "photo" and r["text"].startswith("No pude abrir esa foto")
            ai["read"].assert_not_awaited()
        finally:
            await _clean(user_id)
