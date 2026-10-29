"""La campaña que pregunta (docs/specs/2026-10-29-campana-que-pregunta.md).
Base y Redis reales; la IA, la voz, la subida de archivos y WhatsApp son falsos."""
import io
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image
from sqlalchemy import delete

from app.config import settings
from app.database import AsyncSessionLocal
from app.domain import campaign_builder as cb
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.product import Product
from app.models.sale import Sale
from app.models.user import User
from app.services import campaign_quota
from app.services.banner_service import BannerCopy
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
        "later": MagicMock(return_value=None),
    }
    with patch("app.services.claude_service.generate_campaign_variants", mocks["variants"]), \
         patch("app.services.radio_service.generate_radio_script", mocks["script"]), \
         patch("app.services.radio_service.generate_radio_ad", mocks["audio"]), \
         patch("app.services.storage_service.upload_bytes", mocks["upload"]), \
         patch("app.services.storage_service.read_bytes", mocks["read"]), \
         patch("app.services.banner_service.generate_banner_copy_with_claude", mocks["copy"]), \
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
            assert [c["label"] for c in r["choices"]] == ["Foto de Mica templada", "Subir una foto", "Cartel de colores"]
            r = await _turn(user_id, r["campaign_id"], r["choices"][0]["id"])
            assert r["step"] == "preview" and r["preview"]["kind"] == "image"
            assert r["preview"]["image_url"].endswith(".jpg") and r["preview"]["text"] == VARIANTS[0]
            ai["read"].assert_awaited_with(PHOTO)
            content = ai["upload"].await_args.args[0]
            assert Image.open(io.BytesIO(content)).size == (1080, 1080)  # su foto, cuadrada, con la franja
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
            # Por WhatsApp sigue send_promo (Fase C).
            assert "send_promo" in [t["name"] for t in cs._tools_for("whatsapp")]
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
