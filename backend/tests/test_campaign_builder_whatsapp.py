"""La campaña que pregunta por WhatsApp (Fase C).
Base y Redis reales; la IA, la voz, la subida de archivos y WhatsApp son falsos.
"""
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.domain import campaign_builder as cb
from app.models.product import Product
from app.models.user import User
from app.services import campaign_quota, llm_client
from app.services import copilot_whatsapp_service as cw
from app.services import platform_whatsapp as pw
from app.services.banner_service import BannerCopy
from app.services.meta_client import MetaApiError
from tests.test_campaign_builder import AUDIO, PHOTO, VARIANTS, _camp, _clean, _owner
from tests.test_copilot_whatsapp import FakeRedis
from tests.test_web_push import _add_subs

TO = "+5215512345678"
DELAY = "app.workers.tasks.schedule_campaign.delay"


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


def _jpeg() -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (800, 600), (40, 120, 200)).save(buf, format="JPEG")
    return buf.getvalue()


async def _start(uid, prefill=None) -> dict:
    async with AsyncSessionLocal() as db:
        return await cb.handle(db, await db.get(User, uid), prefill=prefill)


def _action(step: dict) -> AsyncMock:
    return AsyncMock(return_value={
        "reply": step["text"],
        "actions": [{"tool": "build_campaign", "data": {"builder": step}}],
        "pending_confirmation": None,
    })


async def _run(uid, text, redis, *, chat=None, photo_url=None, voice=False):
    """Un mensaje del dueño; devuelve los mocks de lo que se le mandó."""
    async with AsyncSessionLocal() as db:
        owner = await db.get(User, uid)
        with (
            patch.object(cw, "get_redis_optional", AsyncMock(return_value=redis)),
            patch.object(cw, "handle_chat", chat or AsyncMock(
                return_value={"reply": "ok", "actions": [], "pending_confirmation": None})) as hc,
            patch.object(cw, "_note_url", AsyncMock(side_effect=lambda u: u)),
            patch.object(cw, "send_platform_text", AsyncMock(return_value=("w", None))) as st,
            patch.object(cw, "send_platform_buttons", AsyncMock(return_value=("w", None))) as sb,
            patch.object(cw, "send_platform_list", AsyncMock(return_value=("w", None))) as sl,
            patch.object(cw, "send_platform_image", AsyncMock(return_value=("w", None))) as si,
            patch.object(cw, "send_platform_audio", AsyncMock(return_value=("w", None))) as sa,
        ):
            await cw.handle_owner_command(db, owner=owner, from_number=TO, text=text,
                                          voice=voice, photo_url=photo_url)
    return hc, st, sb, sl, si, sa


def _state(redis, uid) -> dict:
    return json.loads(redis.store[f"copilot_wa:{uid}"])


async def _products(uid) -> list[Product]:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Product).where(Product.advertiser_id == uid))).scalars().all()


async def _to_send(uid, redis, what: str = "10% en cargadores este fin de semana"):
    """Arranca la plática y la lleva hasta el cupón o hasta mandar."""
    step = await _start(uid, {"what": what, "format": "text"})
    await _run(uid, "x", redis, chat=_action(step))
    await _run(uid, "Así está bien", redis)       # audiencia dibujada
    _, _, sb, _, _, _ = await _run(uid, "Todos", redis)  # cupón o mandar
    return step, sb


async def _connect_chip(uid) -> None:
    async with AsyncSessionLocal() as db:
        user = await db.get(User, uid)
        user.meta_connection_status = "connected"
        user.meta_phone_number_id = "123456"
        user.meta_token_cipher, user.meta_token_iv, user.meta_token_tag = "c", "i", "t"
        user.messages_remaining = 10
        await db.commit()


class TestLaPlaticaPorWhatsApp:
    @pytest.mark.asyncio
    async def test_caso1_abre_la_platica_por_whatsapp(self, ai):
        # La IA solo elige la herramienta; los botones de la plática siguen solos.
        uid, _ = await _owner()
        try:
            args = {"what": "2x1 en micas"}
            call = llm_client.ToolCall("t1", "build_campaign", args)
            reply = llm_client.ToolReply("", [call], [{"type": "tool_use", "id": "t1",
                                                      "name": "build_campaign", "input": args}])
            completion = AsyncMock(return_value=reply)
            redis = FakeRedis()
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, uid)
                with (
                    patch.object(llm_client, "tool_completion", completion),
                    patch.object(cw, "get_redis_optional", AsyncMock(return_value=redis)),
                    patch("app.services.copilot_service.get_redis_optional", AsyncMock(return_value=None)),
                    patch.object(cw, "_note_url", AsyncMock(side_effect=lambda u: u)),
                    patch.object(cw, "send_platform_text", AsyncMock(return_value=("w", None))),
                    patch.object(cw, "send_platform_buttons", AsyncMock(return_value=("w", None))) as sb,
                    patch.object(cw, "send_platform_list", AsyncMock(return_value=("w", None))),
                ):
                    await cw.handle_owner_command(
                        db, owner=owner, from_number=TO, text="haz una campaña de 2x1 en micas")
            body, buttons = sb.call_args.args[1], sb.call_args.args[2]
            assert "¿Cómo se lo mando?" in body
            assert buttons == [("f:text", "Texto"), ("f:photo", "Con foto"), ("f:audio", "Audio de radio")]
            tools = [t["name"] for t in completion.await_args.kwargs["tools"]]
            assert "build_campaign" in tools and "send_promo" not in tools
            state = _state(redis, uid)
            assert state["builder"]["step"] == "format"
            assert (await _camp(state["builder"]["campaign_id"])).status == "draft"
        finally:
            await _clean(uid)

    @pytest.mark.asyncio
    async def test_caso2_botones_hasta_tres_y_lista_cuando_hay_mas(self, ai):
        uid, _ = await _owner()
        try:
            # Formato: 3 opciones → botones.
            step = await _start(uid, {"what": "2x1 en micas"})
            assert step["step"] == "format"
            _, _, sb, sl, _, _ = await _run(uid, "x", FakeRedis(), chat=_action(step))
            assert [t for _, t in sb.call_args.args[2]] == ["Texto", "Con foto", "Audio de radio"]
            sl.assert_not_called()

            # Estilos: 7 opciones → lista con títulos que caben en WhatsApp.
            step = await _start(uid, {"what": "2x1 en micas", "format": "audio"})
            assert step["step"] == "style"
            _, _, sb, sl, _, _ = await _run(uid, "x", FakeRedis(), chat=_action(step))
            rows = sl.call_args.args[2]
            assert len(rows) == 7 and all(len(t) <= 24 for _, t in rows)
            sb.assert_not_called()
        finally:
            await _clean(uid)

    @pytest.mark.asyncio
    async def test_caso3_la_cuna_llega_como_nota_de_voz(self, ai):
        uid, _ = await _owner()
        try:
            step = await _start(uid, {"what": "2x1 en micas", "format": "audio"})
            redis = FakeRedis()
            await _run(uid, "x", redis, chat=_action(step))
            _, _, sb, _, _, sa = await _run(uid, "Dato curioso", redis)
            sa.assert_awaited_once_with(TO, AUDIO)
            assert "¿Así está bien?" in sb.call_args.args[1]
            assert [t for _, t in sb.call_args.args[2]] == ["Así está bien", "Otra versión", "Cambiar el texto"]
            assert _state(redis, uid)["builder"]["step"] == "preview"
        finally:
            await _clean(uid)

    @pytest.mark.asyncio
    async def test_caso4_su_foto_se_usa_y_la_vista_previa_es_la_imagen(self, ai):
        uid, _ = await _owner()
        try:
            step = await _start(uid, {"what": "2x1 en micas", "format": "photo"})
            assert step["step"] == "photo"
            redis = FakeRedis()
            await _run(uid, "x", redis, chat=_action(step))
            _, st, *_ = await _run(uid, "Subir una foto", redis)
            assert "Mándame la foto" in st.call_args.args[1]

            _, _, _, _, si, _ = await _run(uid, "", redis, photo_url=PHOTO)
            state = _state(redis, uid)
            camp = await _camp(state["builder"]["campaign_id"])
            assert state["builder"]["step"] == "preview"
            assert si.call_args.args[1] == camp.image_url  # la misma que verá el cliente
            assert await _products(uid) == []
        finally:
            await _clean(uid)

    @pytest.mark.asyncio
    async def test_caso5_texto_con_botones_de_vista_previa(self, ai):
        uid, _ = await _owner()
        try:
            step = await _start(uid, {"what": "2x1 en micas", "format": "text"})
            assert step["step"] == "preview" and step["preview"]["kind"] == "text"
            _, _, sb, _, _, _ = await _run(uid, "x", FakeRedis(), chat=_action(step))
            body = sb.call_args.args[1]
            assert VARIANTS[0] in body and "¿Así está bien?" in body
            assert [t for _, t in sb.call_args.args[2]] == ["Así está bien", "Otra versión", "Cambiar el texto"]
        finally:
            await _clean(uid)

    @pytest.mark.asyncio
    async def test_caso6_uno_busca_y_elige_de_la_lista(self, ai):
        uid, (cid,) = await _owner()
        try:
            step = await _start(uid, {"what": "2x1 en micas", "format": "text"})
            redis = FakeRedis()
            await _run(uid, "x", redis, chat=_action(step))
            _, _, sb, _, _, _ = await _run(uid, "Así está bien", redis)   # audiencia dibujada
            assert [t for _, t in sb.call_args.args[2]] == ["Todos", "Los que compraron", "Uno"]
            _, st, _, _, _, _ = await _run(uid, "Uno", redis)            # pide el nombre
            assert "nombre" in st.call_args.args[1].lower()

            _, _, _, _, _, _ = await _run(uid, "Cliente", redis)  # busca
            hit = _state(redis, uid)["builder"]["choices"][0]
            assert hit["label"].startswith("Cliente 0")
            await _run(uid, hit["label"], redis)  # elige de la lista
            state = _state(redis, uid)
            assert state["builder"]["step"] == "send"
            camp = await _camp(state["builder"]["campaign_id"])
            assert camp.segment == {"specific_contacts": [str(cid)]}
        finally:
            await _clean(uid)

    @pytest.mark.asyncio
    async def test_caso7_cupon_con_botones(self, ai):
        uid, (cid,) = await _owner()
        try:
            await _add_subs(uid, cid, 1)
            redis = FakeRedis()
            await _to_send(uid, redis)  # "10% ...": se detiene a preguntar el cupón
            state = _state(redis, uid)
            assert state["builder"]["step"] == "discount"
            assert "10%" in state["builder"]["text"]
            assert [c["label"] for c in state["builder"]["choices"]] == ["Sí", "No"]

            await _run(uid, "Sí", redis)
            assert _state(redis, uid)["builder"]["step"] == "send"
        finally:
            await _clean(uid)

    @pytest.mark.asyncio
    async def test_caso8_manda_desde_el_boton_y_cierra_la_platica(self, ai):
        uid, (cid,) = await _owner()
        try:
            await _add_subs(uid, cid, 1)
            redis = FakeRedis()
            step, sb = await _to_send(uid, redis, what="2x1 en micas")  # sin cupón: directo a mandar
            assert _state(redis, uid)["builder"]["step"] == "send"
            assert [t for _, t in sb.call_args.args[2]] == ["Gratis por web"]

            delay = MagicMock()
            with patch(DELAY, delay):
                _, st, *_ = await _run(uid, "Mandar gratis por web", redis)
            assert "¡Listo!" in st.call_args.args[1]
            assert _state(redis, uid)["builder"] is None
            camp = await _camp(step["campaign_id"])
            assert camp.status == "running"
            delay.assert_called_once_with(step["campaign_id"])
        finally:
            await _clean(uid)

    @pytest.mark.asyncio
    async def test_caso8b_con_chip_el_costo_va_en_el_texto_y_manda_por_los_dos(self, ai):
        uid, _ = await _owner()
        try:
            await _connect_chip(uid)
            redis = FakeRedis()
            step, sb = await _to_send(uid, redis, what="2x1 en micas")
            body = sb.call_args.args[1]
            assert "También por WhatsApp (aprox $" in body
            assert [t for _, t in sb.call_args.args[2]] == ["Gratis por web", "Por WhatsApp"]

            delay = MagicMock()
            with patch(DELAY, delay):
                _, st, *_ = await _run(uid, "Por WhatsApp", redis)
            assert st.call_args.args[1] == "¡Listo! Tu promo va por web y WhatsApp."
            camp = await _camp(step["campaign_id"])
            assert camp.status == "running" and camp.ab_test.get("web_only") is not True
            delay.assert_called_once_with(step["campaign_id"])
        finally:
            await _clean(uid)

    @pytest.mark.asyncio
    async def test_caso8c_un_si_o_tambien_suelto_no_manda_la_campana(self, ai):
        # Con una pregunta de cliente pendiente, "Sí"/"También"/"whatsapp"
        # pueden ser para el cliente: en "mandar" no deben disparar el envío
        # (y menos el de WhatsApp, que Meta cobra).
        uid, _ = await _owner()
        try:
            await _connect_chip(uid)
            redis = FakeRedis()
            step, _ = await _to_send(uid, redis, what="2x1 en micas")
            assert _state(redis, uid)["builder"]["step"] == "send"

            delay = MagicMock()
            with patch(DELAY, delay):
                for said in ("Sí", "También", "whatsapp"):
                    _, _, sb, *_ = await _run(uid, said, redis)
                    delay.assert_not_called()
                    assert _state(redis, uid)["builder"]["step"] == "send"
                    assert "También por WhatsApp (aprox $" in sb.call_args.args[1]
            assert (await _camp(step["campaign_id"])).status == "draft"
        finally:
            await _clean(uid)

    @pytest.mark.asyncio
    async def test_caso9_retoma_el_borrador_donde_iba(self, ai):
        uid, _ = await _owner()
        try:
            step = await _start(uid, {"what": "2x1 en micas", "format": "text"})
            assert step["step"] == "preview"
            resume = await _start(uid)  # vuelve a pedir campaña: hay un borrador
            assert resume["step"] == "resume"
            redis = FakeRedis()
            _, _, sb, _, _, _ = await _run(uid, "x", redis, chat=_action(resume))
            assert [t for _, t in sb.call_args.args[2]] == ["Seguir", "Empezar otra"]
            await _run(uid, "Seguir", redis)
            assert _state(redis, uid)["builder"]["step"] == "preview"
        finally:
            await _clean(uid)

    @pytest.mark.asyncio
    async def test_caso9b_empezar_otra_abre_una_campana_nueva(self, ai):
        uid, _ = await _owner()
        try:
            draft = await _start(uid, {"what": "2x1 en micas", "format": "text"})
            assert draft["step"] == "preview"
            resume = await _start(uid)
            assert resume["step"] == "resume"
            redis = FakeRedis()
            await _run(uid, "x", redis, chat=_action(resume))
            _, st, *_ = await _run(uid, "Empezar otra", redis)
            state = _state(redis, uid)
            assert state["builder"]["step"] == "what" and state["builder"]["campaign_id"] is None
            assert "¿Qué quieres anunciar?" in st.call_args.args[1]

            await _run(uid, "2x1 en fundas", redis)
            new = _state(redis, uid)["builder"]
            assert new["step"] == "format" and new["campaign_id"] != draft["campaign_id"]
            assert (await _camp(draft["campaign_id"])).status == "draft"  # el viejo sigue intacto
        finally:
            await _clean(uid)

    @pytest.mark.asyncio
    async def test_caso10_salir_deja_el_borrador(self, ai):
        uid, _ = await _owner()
        try:
            step = await _start(uid, {"what": "2x1 en micas"})
            assert step["step"] == "format"
            redis = FakeRedis()
            await _run(uid, "x", redis, chat=_action(step))
            hc, st, *_ = await _run(uid, "salir", redis)
            hc.assert_not_awaited()
            assert _state(redis, uid)["builder"] is None
            assert "borrador" in st.call_args.args[1]
            assert (await _camp(step["campaign_id"])).status == "draft"
        finally:
            await _clean(uid)

    @pytest.mark.asyncio
    async def test_caso11_foto_en_el_paso_no_se_vuelve_producto(self, ai):
        uid, _ = await _owner()
        try:
            step = await _start(uid, {"what": "2x1 en micas", "format": "photo"})
            redis = FakeRedis()
            await _run(uid, "x", redis, chat=_action(step))
            hc, st, *_ = await _run(uid, "", redis, photo_url=PHOTO)
            hc.assert_not_awaited()  # no pasó por el Copiloto de productos
            sent = [c.args[1] for c in st.await_args_list]
            assert cw._PHOTO_PROMPT not in sent
            assert await _products(uid) == []
            assert _state(redis, uid)["builder"]["step"] == "preview"
        finally:
            await _clean(uid)

    def test_caso12_nota_de_voz_sigue_la_promo_rapida(self):
        from app.services.copilot_service import _tools_for

        voz = [t["name"] for t in _tools_for("voz")]
        escrito = [t["name"] for t in _tools_for("whatsapp")]
        assert "send_promo" in voz and "build_campaign" not in voz
        assert "build_campaign" in escrito and "send_promo" not in escrito

    @pytest.mark.asyncio
    async def test_caso14_sin_redis_no_abre_el_armador(self, ai):
        uid, _ = await _owner()
        try:
            step = await _start(uid, {"what": "2x1 en micas"})
            _, st, sb, sl, _, _ = await _run(uid, "x", None, chat=_action(step))
            assert "panel" in st.call_args.args[1]
            sb.assert_not_called()
            sl.assert_not_called()
        finally:
            await _clean(uid)


class TestLosMensajesDeWhatsApp:
    @pytest.mark.asyncio
    async def test_caso13_si_meta_rechaza_las_opciones_va_el_texto(self):
        with (
            patch.object(pw, "platform_enabled", return_value=True),
            patch.object(pw, "platform_token", AsyncMock(return_value="tok")),
            patch.object(pw, "graph_request", AsyncMock(side_effect=MetaApiError("boom", status=400))),
            patch.object(pw, "send_platform_text", AsyncMock(return_value=("w", None))) as st,
        ):
            assert await pw.send_platform_list(TO, "¿Estilo?", [("s:radio", "Anuncio"), ("s:trivia", "Trivia")]) == ("w", None)
        body = st.call_args.args[1]
        assert "1. Anuncio" in body and "2. Trivia" in body

    @pytest.mark.asyncio
    async def test_la_lista_manda_maximo_diez_filas_y_titulos_cortos(self):
        gr = AsyncMock(return_value={"messages": [{"id": "w"}]})
        with (
            patch.object(pw, "platform_enabled", return_value=True),
            patch.object(pw, "platform_token", AsyncMock(return_value="tok")),
            patch.object(pw, "graph_request", gr),
        ):
            await pw.send_platform_list(TO, "¿Estilo?", [(f"s:{i}", "x" * 40) for i in range(12)])
        body = gr.await_args.kwargs["body"]
        rows = body["interactive"]["action"]["sections"][0]["rows"]
        assert body["interactive"]["type"] == "list" and len(rows) == 10
        assert all(len(r["title"]) <= 24 for r in rows)

    @pytest.mark.asyncio
    async def test_la_imagen_de_la_vista_previa_va_por_link(self):
        gr = AsyncMock(return_value={"messages": [{"id": "w"}]})
        with (
            patch.object(pw, "platform_enabled", return_value=True),
            patch.object(pw, "platform_token", AsyncMock(return_value="tok")),
            patch.object(pw, "graph_request", gr),
        ):
            await pw.send_platform_image(TO, "https://cdn.test/a.jpg", caption="Así la ve")
        body = gr.await_args.kwargs["body"]
        assert body["type"] == "image"
        assert body["image"] == {"link": "https://cdn.test/a.jpg", "caption": "Así la ve"}
