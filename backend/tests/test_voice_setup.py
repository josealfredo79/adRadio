"""Configurar el bot por voz (services/voice_setup.py, api/v1/voice_setup.py).

Lo crítico: lo que regresa el modelo se valida antes de mostrarse o
guardarse (nunca horarios imposibles ni precios negativos), las correcciones
mandan el borrador actual, y "aplicar" deja el bot y el catálogo listos sin
duplicar productos."""
import json
import uuid
from io import BytesIO
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, UploadFile
from sqlalchemy import delete, select
from starlette.datastructures import Headers
from starlette.requests import Request

from app.api.v1.voice_setup import (
    ApplyBody,
    PreviewBody,
    SpeakBody,
    apply,
    listen,
    preview,
    speak,
)
from app.database import AsyncSessionLocal, engine
from app.models.product import Product
from app.models.user import User
from app.services import voice_setup as vs

MODEL_JSON = {
    "business_category": "barbería",
    "city": "Tlaxiaco",
    "address": "Calle Hidalgo 12, centro",
    "business_hours": {"mon": ["10:00", "20:00"], "tue": ["10:00", "20:00"], "wed": ["10:00", "20:00"],
                       "thu": ["10:00", "20:00"], "fri": ["10:00", "20:00"], "sat": ["10:00", "18:00"], "sun": None},
    "services": [{"name": "Corte", "price": 150, "description": None},
                 {"name": "Barba", "price": "$100", "description": "con toalla caliente"}],
    "payment_methods": ["efectivo", "transferencia"],
    "policies": ["Si llegas 15 minutos tarde se reagenda"],
    "faqs": [{"q": "¿Atienden niños?", "a": "Sí, desde los 3 años"}],
    "notes": [],
}


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/api/v1/voice-setup/listen", "headers": [],
                    "client": (f"test-{uuid.uuid4()}", 1), "query_string": b""})


def _audio(data: bytes, ctype: str = "audio/webm") -> UploadFile:
    return UploadFile(file=BytesIO(data), filename="nota.webm", headers=Headers({"content-type": ctype}))


class TestSanitize:
    def test_valid_profile_passes_and_prices_are_numbers(self):
        p = vs.sanitize_profile(MODEL_JSON)
        assert [s["price"] for s in p["services"]] == [150.0, 100.0]
        assert p["business_hours"]["sun"] is None and p["business_hours"]["sat"] == ["10:00", "18:00"]

    @pytest.mark.parametrize("hours", [
        {"mon": ["25:00", "26:00"]},           # horas imposibles
        {"mon": ["18:00", "09:00"]},           # cierra antes de abrir
        {"mon": "de 9 a 6"},                   # texto en vez de rango
        "lunes a viernes",                     # ni siquiera un dict
    ])
    def test_bad_hours_never_reach_the_calendar(self, hours):
        assert vs.sanitize_profile({"business_hours": hours})["business_hours"] is None

    @pytest.mark.parametrize("price,expected", [(-5, None), ("gratis", None), ("$1,500", 1500.0), (True, None), (99.5, 99.5)])
    def test_prices(self, price, expected):
        p = vs.sanitize_profile({"services": [{"name": "X", "price": price}]})
        assert p["services"][0]["price"] == expected

    def test_garbage_items_are_dropped_and_lengths_capped(self):
        p = vs.sanitize_profile({
            "services": ["corte", {"name": ""}, {"name": "A" * 500, "price": 1}],
            "faqs": [{"q": "sin respuesta"}, "x"],
            "payment_methods": [None, 3, "efectivo"],
        })
        assert len(p["services"]) == 1 and len(p["services"][0]["name"]) == 200
        assert p["faqs"] == [] and p["payment_methods"] == ["efectivo"]

    def test_parse_json_inside_code_fences(self):
        raw = "Claro, aquí está:\n```json\n" + json.dumps({"city": "Oaxaca"}) + "\n```"
        assert vs._parse_json(raw) == {"city": "Oaxaca"}


class TestRender:
    def test_instructions_read_like_the_owner_said_them(self):
        text = vs.render_instructions(MODEL_JSON)
        assert "Ubicación: Calle Hidalgo 12, centro, Tlaxiaco" in text
        assert "Sábado 10:00–18:00" in text and "Domingo cerrado" in text
        assert "- Corte — $150" in text and "- Barba — $100 (con toalla caliente)" in text
        assert "Formas de pago: efectivo, transferencia" in text
        assert "P: ¿Atienden niños?\nR: Sí, desde los 3 años" in text

    def test_never_exceeds_the_field_limit(self):
        big = {"services": [{"name": f"Servicio {i} " + "x" * 150, "price": i} for i in range(40)]}
        assert len(vs.render_instructions(big)) <= vs.MAX_INSTRUCTIONS

    def test_empty_profile_renders_nothing(self):
        assert vs.render_instructions({}) == ""


class TestMergeInstructions:
    """Armar la página de un negocio que ya tiene bot: se edita, no se rehace."""

    def test_keeps_payments_faqs_and_own_text_it_was_not_told_about(self):
        existing = vs.render_instructions(MODEL_JSON) + "\n\nNunca des descuentos por WhatsApp."
        out = vs.merge_instructions(existing, {"city": "Oaxaca", "address": "Calle Juárez 3"})
        assert "Ubicación: Calle Juárez 3, Oaxaca" in out and "Calle Hidalgo" not in out
        assert "Formas de pago: efectivo, transferencia" in out
        assert "P: ¿Atienden niños?" in out and "Nunca des descuentos" in out
        assert "- Corte — $150" in out

    def test_only_adds_the_topics_that_were_missing(self):
        out = vs.merge_instructions("Horario: de lunes a viernes", {"payment_methods": ["efectivo"]})
        assert out == "Horario: de lunes a viernes\n\nFormas de pago: efectivo"

    def test_empty_account_gets_the_full_text(self):
        assert vs.merge_instructions(None, MODEL_JSON) == vs.render_instructions(MODEL_JSON)

    def test_same_profile_twice_changes_nothing(self):
        once = vs.merge_instructions(None, MODEL_JSON)
        assert vs.merge_instructions(once, MODEL_JSON) == once

    def test_respects_the_field_limit(self):
        big = {"services": [{"name": f"Servicio {i} " + "x" * 150, "price": i} for i in range(40)]}
        assert len(vs.merge_instructions("Horario: abierto", big)) <= vs.MAX_INSTRUCTIONS


class TestParseInstructions:
    def test_reads_back_what_render_wrote(self):
        parsed, free = vs.parse_instructions(vs.render_instructions(MODEL_JSON))
        assert parsed["payment_methods"] == ["efectivo", "transferencia"]
        assert parsed["policies"] == ["Si llegas 15 minutos tarde se reagenda"]
        assert parsed["faqs"] == [{"q": "¿Atienden niños?", "a": "Sí, desde los 3 años"}]
        assert parsed["address"] == "Calle Hidalgo 12, centro, Tlaxiaco" and free is False

    def test_own_text_is_flagged_not_parsed(self):
        parsed, free = vs.parse_instructions("Somos una barbería familiar, siempre sonríe.")
        assert free is True and parsed["faqs"] == [] and parsed["payment_methods"] == []

    def test_nothing_is_nothing(self):
        assert vs.parse_instructions(None)[1] is False


class TestExtract:
    @pytest.mark.asyncio
    async def test_correction_sends_the_current_draft(self):
        fake = AsyncMock(return_value=json.dumps(MODEL_JSON))
        with patch.object(vs, "chat_completion", fake):
            out = await vs.extract_profile("no, el sábado cerramos a las 6", current=MODEL_JSON, business_name="Don Pepe")
        prompt = fake.await_args.args[0][0]["content"]
        assert "BORRADOR ACTUAL" in prompt and "Calle Hidalgo" in prompt and "el sábado cerramos" in prompt
        assert "NUNCA inventes" in fake.await_args.kwargs["system"]
        assert out["city"] == "Tlaxiaco"


class TestListenEndpoint:
    @pytest.mark.asyncio
    async def test_text_fallback(self):
        user = User(id=uuid.uuid4(), email="x@test.com", password_hash="x", bot_instructions="viejas")
        with patch("app.api.v1.voice_setup.extract_profile", AsyncMock(return_value=vs.sanitize_profile(MODEL_JSON))):
            out = await listen(request=_request(), audio=None, text="Abrimos de 10 a 8", draft=None, question=None, asked=None, current_user=user)
        assert out["transcript"] == "Abrimos de 10 a 8"
        assert out["replaces_existing_instructions"] is True
        assert "Lunes 10:00–20:00" in out["hours_text"]

    @pytest.mark.asyncio
    async def test_audio_goes_through_whisper(self):
        user = User(id=uuid.uuid4(), email="x@test.com", password_hash="x")
        whisper = AsyncMock(return_value="Somos barbería, el corte cuesta 150")
        with patch("app.api.v1.voice_setup.transcribe_audio_bytes", whisper), \
             patch("app.api.v1.voice_setup.extract_profile", AsyncMock(return_value=vs.sanitize_profile({}))):
            out = await listen(request=_request(), audio=_audio(b"ogg-bytes", "audio/webm;codecs=opus"),
                               text=None, draft=None, question=None, asked=None, current_user=user)
        assert whisper.await_args.args == (b"ogg-bytes", "audio/webm")
        assert out["transcript"].startswith("Somos barbería")

    @pytest.mark.asyncio
    async def test_unintelligible_audio_asks_to_retry(self):
        user = User(id=uuid.uuid4(), email="x@test.com", password_hash="x")
        with patch("app.api.v1.voice_setup.transcribe_audio_bytes", AsyncMock(return_value=None)), \
             pytest.raises(HTTPException) as exc:
            await listen(request=_request(), audio=_audio(b"ruido"), text=None, draft=None, question=None, asked=None, current_user=user)
        assert exc.value.status_code == 422 and "escuchar" in exc.value.detail

    @pytest.mark.asyncio
    async def test_too_long_and_empty(self):
        user = User(id=uuid.uuid4(), email="x@test.com", password_hash="x")
        with pytest.raises(HTTPException) as exc:
            await listen(request=_request(), audio=_audio(b"x" * (10 * 1024 * 1024 + 1)), text=None, draft=None, question=None, asked=None, current_user=user)
        assert exc.value.status_code == 413
        with pytest.raises(HTTPException) as exc:
            await listen(request=_request(), audio=None, text="   ", draft=None, question=None, asked=None, current_user=user)
        assert exc.value.status_code == 400

    @pytest.mark.asyncio
    async def test_model_failure_is_a_friendly_error(self):
        user = User(id=uuid.uuid4(), email="x@test.com", password_hash="x")
        with patch("app.api.v1.voice_setup.extract_profile", AsyncMock(side_effect=ValueError("no json"))), \
             pytest.raises(HTTPException) as exc:
            await listen(request=_request(), audio=None, text="hola", draft=None, question=None, asked=None, current_user=user)
        assert exc.value.status_code == 502


class TestApply:
    @pytest.mark.asyncio
    async def test_configures_bot_hours_and_catalog_without_duplicates(self):
        await engine.dispose()
        async with AsyncSessionLocal() as db:
            user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Don Pepe")
            db.add(user)
            await db.flush()
            db.add(Product(advertiser_id=user.id, name="corte", price=120, active=True))  # ya existía, otro precio
            await db.commit()
            uid = user.id
        try:
            async with AsyncSessionLocal() as db:
                u = await db.get(User, uid)
                out = await apply(body=ApplyBody(profile=MODEL_JSON), db=db, current_user=u)
            assert out == {"instructions_chars": out["instructions_chars"], "hours_set": True,
                           "products_created": 1, "products_updated": 1}
            async with AsyncSessionLocal() as db:
                u = await db.get(User, uid)
                prods = {p.name: float(p.price) for p in
                         (await db.execute(select(Product).where(Product.advertiser_id == uid))).scalars().all()}
            assert prods == {"corte": 150.0, "Barba": 100.0}
            assert u.business_hours["sun"] is None and u.city == "Tlaxiaco"
            assert "Servicios y precios" in u.bot_instructions
        finally:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(Product).where(Product.advertiser_id == uid))
                await db.execute(delete(User).where(User.id == uid))
                await db.commit()
            await engine.dispose()

    @pytest.mark.asyncio
    async def test_nothing_to_save(self):
        user = User(id=uuid.uuid4(), email="x@test.com", password_hash="x")
        with pytest.raises(HTTPException) as exc:
            await apply(body=ApplyBody(profile={}), db=AsyncMock(), current_user=user)
        assert exc.value.status_code == 400



class TestConversation:
    """La carita que platica: pregunta lo que falta, de a una cosa, sin repetir."""

    def test_asks_in_priority_order_and_never_repeats(self):
        empty = vs.sanitize_profile({})
        assert vs.next_question(empty, [])["field"] == "services"
        assert vs.next_question(empty, ["services"])["field"] == "hours"
        assert vs.next_question(vs.sanitize_profile(MODEL_JSON), []) is None
        assert vs.next_question(empty, ["services", "hours", "location", "payments"]) is None

    @pytest.mark.parametrize("hhmm,said", [("19:00", "7"), ("09:30", "9 y media"), ("12:00", "12"), ("00:00", "12"), ("08:15", "8:15")])
    def test_times_are_said_like_people_say_them(self, hhmm, said):
        assert vs.speak_time(hhmm) == said

    def test_hours_are_grouped_when_spoken(self):
        h = {"mon": None, "tue": ["09:00", "19:00"], "wed": ["09:00", "19:00"], "thu": ["09:00", "19:00"],
             "fri": ["09:00", "19:00"], "sat": ["09:00", "19:00"], "sun": ["10:00", "14:00"]}
        assert vs._speak_hours(h) == "Abres de martes a sábado de 9 a 7, y el domingo de 10 a 2; los lunes cierras"

    def test_closed_days_are_plural(self):
        h = {d: ["09:00", "19:00"] for d in ("mon", "tue", "wed", "thu", "fri", "sat")} | {"sun": None}
        assert vs._speak_hours(h) == "Abres de lunes a sábado de 9 a 7; los domingos cierras"
        h2 = {d: ["09:00", "19:00"] for d in ("mon", "tue", "wed", "thu", "fri")} | {"sat": None, "sun": None}
        assert vs._speak_hours(h2).endswith("los sábados y domingos cierras")

    def test_reply_says_what_was_noted_then_asks(self):
        p = {"services": [{"name": "Corte", "price": 150}]}
        reply = vs.spoken_reply(p, None, vs.next_question(p, []))
        assert reply.startswith("¡Muy bien! Ya anoté 1 servicio.") and "horario" in reply

    def test_reply_when_nothing_new_was_understood(self):
        assert vs.spoken_reply(MODEL_JSON, MODEL_JSON, None).startswith("¡Anotado!")
        assert "no alcancé" in vs.spoken_reply({}, None, vs.next_question({}, []))

    def test_spoken_summary_reads_naturally(self):
        text = vs.spoken_summary(MODEL_JSON)
        assert "Vendes corte en 150 pesos, barba en 100 pesos." in text
        assert "Te pagan con efectivo y transferencia." in text

    @pytest.mark.asyncio
    async def test_answer_to_a_question_carries_the_question_and_moves_on(self):
        user = User(id=uuid.uuid4(), email="x@test.com", password_hash="x")
        only_services = vs.sanitize_profile({"services": [{"name": "Corte", "price": 150}]})
        extract = AsyncMock(return_value=only_services)
        with patch("app.api.v1.voice_setup.extract_profile", extract):
            out = await listen(request=_request(), audio=None, text="de 9 a 7", draft=json.dumps(only_services),
                               question="hours", asked="services", current_user=user)
        assert extract.await_args.kwargs["question_text"].startswith("¿En qué horario")
        # Contestó (aunque no se entendiera el horario): no se vuelve a preguntar; sigue la ubicación.
        assert out["next_question"]["field"] == "location"
        assert out["say"].startswith("¡Anotado!")

    @pytest.mark.asyncio
    async def test_speak_returns_audio(self):
        user = User(id=uuid.uuid4(), email="x@test.com", password_hash="x")
        with patch("app.services.radio.tts._tts_edge", AsyncMock(return_value=b"mp3")) as tts:
            resp = await speak(request=_request(), body=SpeakBody(text="  ¡Hola!   ¿qué vendes? "), current_user=user)
        assert resp.body == b"mp3" and resp.media_type == "audio/mpeg"
        assert tts.await_args.args[:2] == ("¡Hola! ¿qué vendes?", "es-MX-DaliaNeural")

    @pytest.mark.asyncio
    async def test_speak_failure_lets_the_browser_voice_take_over(self):
        user = User(id=uuid.uuid4(), email="x@test.com", password_hash="x")
        with patch("app.services.radio.tts._tts_edge", AsyncMock(side_effect=RuntimeError("down"))), \
             pytest.raises(HTTPException) as exc:
            await speak(request=_request(), body=SpeakBody(text="hola"), current_user=user)
        assert exc.value.status_code == 503



class TestPreview:
    @pytest.mark.asyncio
    async def test_resumes_a_landing_draft_without_calling_the_ai(self):
        user = User(id=uuid.uuid4(), email="x@test.com", password_hash="x")
        with patch("app.api.v1.voice_setup.extract_profile", AsyncMock()) as ai:
            out = await preview(body=PreviewBody(profile={"services": [{"name": "Taco", "price": 15}], "bogus": 1}),
                                current_user=user)
        ai.assert_not_awaited()
        assert out["profile"]["services"] == [{"name": "Taco", "price": 15.0, "description": None}]
        assert "bogus" not in out["profile"]
        assert out["next_question"]["field"] == "hours"
