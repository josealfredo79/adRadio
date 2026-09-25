""""Déjame preguntarle al dueño" — pruebas sin BD (la sesión se simula).

Cubre: el marcador que emite el bot cuando no sabe algo, que ese modo solo se
active con ask_owner (el widget, el laboratorio y los workers usan el mismo
prompt y no deben verlo), el envío por el número central con respaldo de
plantilla, y el ciclo pregunta → respuesta del dueño → cliente + aprendizaje.
"""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.knowledge_base import KnowledgeBase
from app.models.owner_question import OwnerQuestion
from app.models.user import User
from app.services import owner_question_service as svc
from app.services import platform_whatsapp
from app.services.claude_service import (
    OWNER_QUESTION_MARKER,
    generate_bot_response,
    parse_owner_question,
)
from app.services.meta_client import MetaApiError


class TestParseOwnerQuestion:
    def test_extracts_question(self):
        assert parse_owner_question(f"{OWNER_QUESTION_MARKER} ¿Tienen envío?", "x") == "¿Tienen envío?"

    def test_tolerates_prefix_accent_colon_and_newlines(self):
        reply = "Claro 😊\n[[ preguntar_al_dueño ]]: ¿Abren\n el domingo?"
        assert parse_owner_question(reply, "x") == "¿Abren el domingo?"

    def test_empty_question_falls_back_to_customer_text(self):
        assert parse_owner_question(OWNER_QUESTION_MARKER, "¿tienen tacos?") == "¿tienen tacos?"

    def test_normal_reply_is_not_a_question(self):
        assert parse_owner_question("Abrimos de 9 a 6 😊", "x") is None
        assert parse_owner_question(None, "x") is None


class TestPromptMode:
    async def _system_for(self, ask_owner: bool) -> str:
        with patch("app.services.claude_service.chat_completion", new=AsyncMock(return_value="ok")) as cc:
            await generate_bot_response(
                advertiser_context="",
                conversation_history=[],
                user_message="¿Tienen envío?",
                business_name="Taquería Don Pepe",
                ask_owner=ask_owner,
            )
        return cc.call_args.kwargs["system"]

    async def test_ask_owner_prompt_uses_marker(self):
        assert OWNER_QUESTION_MARKER in await self._system_for(True)

    async def test_default_prompt_never_mentions_marker(self):
        # widget / laboratorio / workers no manejan el marcador: si lo vieran,
        # se lo mandarían crudo al cliente.
        system = await self._system_for(False)
        assert OWNER_QUESTION_MARKER not in system
        assert "No tengo ese dato a la mano" in system


class TestPlatformSend:
    def _enable(self, monkeypatch):
        monkeypatch.setattr(platform_whatsapp.settings, "IARADIO_WA_PHONE_NUMBER_ID", "999")
        monkeypatch.setattr(platform_whatsapp.settings, "IARADIO_WA_TOKEN", "tok")

    async def test_disabled_without_config(self, monkeypatch):
        monkeypatch.setattr(platform_whatsapp.settings, "IARADIO_WA_PHONE_NUMBER_ID", "")
        assert await platform_whatsapp.send_platform_text("+5215511111111", "hola") == (None, "platform_not_configured")

    async def test_free_form_first(self, monkeypatch):
        self._enable(monkeypatch)
        gr = AsyncMock(return_value={"messages": [{"id": "wamid.1"}]})
        with patch.object(platform_whatsapp, "graph_request", gr):
            assert await platform_whatsapp.send_platform_text("+5215511111111", "hola") == ("wamid.1", None)
        assert gr.call_count == 1
        assert gr.call_args.kwargs["body"]["type"] == "text"

    async def test_falls_back_to_template_outside_window(self, monkeypatch):
        self._enable(monkeypatch)
        gr = AsyncMock(side_effect=[MetaApiError("re-engagement", status=400, code=131047), {"messages": [{"id": "wamid.2"}]}])
        with patch.object(platform_whatsapp, "graph_request", gr):
            wamid, err = await platform_whatsapp.send_platform_text("+5215511111111", "Línea 1\n\nLínea    2")
        assert (wamid, err) == ("wamid.2", None)
        template = gr.call_args.kwargs["body"]["template"]
        # Meta rechaza parámetros con saltos de línea o espacios repetidos.
        assert template["components"][0]["parameters"][0]["text"] == "Línea 1 Línea 2"


def _owner(**kw) -> User:
    defaults = {
        "id": uuid.uuid4(),
        "business_name": "Taquería Don Pepe",
        "bot_name": "Pepe Bot",
        "whatsapp_number": "+5215512345678",
    }
    defaults.update(kw)
    return User(**defaults)


def _db(*execute_results):
    """Sesión simulada: cada db.execute() devuelve el siguiente resultado."""
    db = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    results = []
    for r in execute_results:
        res = MagicMock()
        res.scalars.return_value.all.return_value = r if isinstance(r, list) else [r]
        res.scalar_one_or_none.return_value = r if not isinstance(r, list) else None
        results.append(res)
    db.execute = AsyncMock(side_effect=results)
    return db


class TestEscalate:
    async def test_sends_to_owner_and_holds_customer(self):
        owner, db = _owner(), _db()
        with patch.object(svc, "send_platform_text", AsyncMock(return_value=("wamid.owner", None))) as sp:
            reply = await svc.escalate_to_owner(
                db, advertiser=owner, contact_id=uuid.uuid4(), customer_phone="+5215599999999",
                customer_name="Ana", question="¿Tienen envío?",
            )
        assert "Déjame confirmarlo" in reply
        oq = db.add.call_args.args[0]
        assert isinstance(oq, OwnerQuestion) and oq.owner_wamid == "wamid.owner"
        assert sp.call_args.args[0] == "+5215512345678"
        assert "¿Tienen envío?" in sp.call_args.args[1]

    async def test_unreachable_owner_does_not_leave_customer_waiting(self):
        owner, db = _owner(), _db()
        with patch.object(svc, "send_platform_text", AsyncMock(return_value=(None, "boom"))):
            reply = await svc.escalate_to_owner(
                db, advertiser=owner, contact_id=None, customer_phone="+52", customer_name="Ana", question="?",
            )
        assert "No tengo ese dato" in reply
        assert db.add.call_args.args[0].status == "undeliverable"


class TestOwnerAnswer:
    def _question(self, owner: User) -> OwnerQuestion:
        return OwnerQuestion(
            id=uuid.uuid4(), advertiser_id=owner.id, contact_id=uuid.uuid4(),
            customer_phone="+5215599999999", question="¿Tienen envío?", status="pending",
        )

    async def test_answer_reaches_customer_and_is_learned(self):
        owner = _owner()
        oq = self._question(owner)
        db = _db([owner], oq)  # 1) dueños por número, 2) pregunta citada
        with (
            patch.object(svc, "send_platform_text", AsyncMock(return_value=("w", None))) as sp,
            patch.object(svc, "send_whatsapp", AsyncMock(return_value=("wamid.c", None))) as sw,
            patch.object(svc, "chat_completion", AsyncMock(return_value="¡Sí! Enviamos por $30 😊")),
            patch.object(svc, "get_embedding", AsyncMock(return_value=[0.0] * 1024)),
            patch.object(svc, "publish_conversation_event", AsyncMock()),
        ):
            await svc.handle_owner_message(db, from_number="+5215512345678", text="si, 30 pesos", context_wamid="wamid.owner")

        assert sw.call_args.args == ("+5215599999999", "¡Sí! Enviamos por $30 😊")
        assert oq.status == "answered" and oq.answer == "si, 30 pesos"
        learned = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], KnowledgeBase)]
        assert learned and "¿Tienen envío?" in learned[0].chunk_text and "30 pesos" in learned[0].chunk_text
        assert "Listo" in sp.call_args.args[1]

    async def test_several_pending_without_quote_asks_which(self):
        owner = _owner()
        db = _db([owner], [self._question(owner), self._question(owner)])
        with patch.object(svc, "send_platform_text", AsyncMock(return_value=("w", None))) as sp, \
                patch.object(svc, "send_whatsapp", AsyncMock()) as sw, \
                patch.object(svc, "chat_completion", AsyncMock(return_value="SI")), \
                patch("app.services.copilot_whatsapp_service.has_pending_confirmation", AsyncMock(return_value=False)):
            await svc.handle_owner_message(db, from_number="+5215512345678", text="sí", context_wamid=None)
        sw.assert_not_called()
        assert "Responder" in sp.call_args.args[1]

    async def test_unknown_number_gets_help(self):
        db = _db([])
        with patch.object(svc, "send_platform_text", AsyncMock(return_value=("w", None))) as sp:
            await svc.handle_owner_message(db, from_number="+5210000000000", text="hola", context_wamid=None)
        assert "No encontré una cuenta" in sp.call_args.args[1]

    async def test_untranscribed_voice_note_asks_again(self):
        owner = _owner()
        db = _db([owner], [self._question(owner)])
        with patch.object(svc, "send_platform_text", AsyncMock(return_value=("w", None))) as sp, \
                patch.object(svc, "send_whatsapp", AsyncMock()) as sw:
            await svc.handle_owner_message(
                db, from_number="+5215512345678", text="[audio: transcripción no disponible]", context_wamid=None,
            )
        sw.assert_not_called()
        assert "No alcancé a entender" in sp.call_args.args[1]


def test_number_variants_cover_mx_mobile_prefix():
    v = svc._number_variants("+5215512345678")
    assert {"+5215512345678", "5215512345678", "+525512345678", "525512345678"} <= set(v)


class TestOwnerNumber:
    def test_prefers_personal_phone(self):
        assert svc.owner_number(_owner(phone="+5215588887777", whatsapp_number="+5215512345678")) == "+5215588887777"

    def test_never_the_bots_own_number(self):
        # whatsapp_number = el número conectado del bot (con o sin el 1 móvil):
        # mandarle ahí el aviso sería que el negocio se escriba a sí mismo.
        owner = _owner(phone=None, whatsapp_number="+5215512345678", meta_display_phone_number="+52 55 1234 5678")
        assert svc.owner_number(owner) is None

    def test_legacy_accounts_with_only_whatsapp_number_still_notified(self):
        assert svc.owner_number(_owner(phone=None, whatsapp_number="+525599990000")) == "+525599990000"


class TestRoutingToCopilot:
    """Un mensaje del dueño que no contesta a un cliente es una instrucción
    para el Copiloto."""

    async def _route(self, db, text, classifier="NO"):
        with (
            patch.object(svc, "send_platform_text", AsyncMock(return_value=("w", None))),
            patch.object(svc, "send_whatsapp", AsyncMock()) as sw,
            patch.object(svc, "chat_completion", AsyncMock(return_value=classifier)),
            patch("app.services.copilot_whatsapp_service.has_pending_confirmation", AsyncMock(return_value=False)),
            patch("app.services.copilot_whatsapp_service.handle_owner_command", AsyncMock()) as cmd,
        ):
            await svc.handle_owner_message(db, from_number="+5215512345678", text=text, context_wamid=None)
        return cmd, sw

    async def test_no_pending_questions_goes_to_copilot(self):
        owner = _owner()
        cmd, sw = await self._route(_db([owner], []), "¿cuántas citas tengo mañana?")
        cmd.assert_awaited_once()
        assert cmd.call_args.kwargs["owner"] is owner
        sw.assert_not_called()

    async def test_instruction_while_a_question_is_pending_goes_to_copilot(self):
        owner = _owner()
        oq = OwnerQuestion(advertiser_id=owner.id, customer_phone="+52", question="¿Tienen envío?", status="pending")
        cmd, sw = await self._route(_db([owner], [oq]), "manda la promo 2x1 a todos", classifier="NO")
        cmd.assert_awaited_once()
        sw.assert_not_called()
        assert oq.status == "pending"
