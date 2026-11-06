"""Contestar desde el Inbox cierra las preguntas pendientes del central de ese
cliente (owner_question_service.close_for_inbox_reply). BD real.

Antes: el dueño contestaba en el Inbox y la pregunta seguía "pending"; su
siguiente mensaje al central (p. ej. una orden para el Copiloto) podía tomarse
como respuesta a ese cliente y mandársela otra vez."""
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import delete, select

from app.api.v1.conversations import ReplyBody, reply_to_conversation
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.message import Message
from app.models.owner_question import OwnerQuestion
from app.models.user import User
from app.services import owner_question_service as svc

OWNER_PHONE = "+5215512345678"


async def _setup():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="CityCell",
                    whatsapp_number=f"+52155{uuid.uuid4().int % 10**8:08d}")
        db.add(user)
        await db.flush()
        ana = Contact(advertiser_id=user.id, name="Ana", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        luis = Contact(advertiser_id=user.id, name="Luis", phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        db.add_all([ana, luis])
        await db.flush()
        conv = Conversation(advertiser_id=user.id, contact_id=ana.id, messages=[])
        db.add(conv)
        q_ana = OwnerQuestion(advertiser_id=user.id, contact_id=ana.id, customer_phone=ana.phone,
                              question="¿Tienen fundas?", owner_wamid=f"wamid.{uuid.uuid4().hex}")
        q_luis = OwnerQuestion(advertiser_id=user.id, contact_id=luis.id, customer_phone=luis.phone,
                               question="¿Abren el domingo?", owner_wamid=f"wamid.{uuid.uuid4().hex}")
        db.add_all([q_ana, q_luis])
        await db.commit()
        return user.id, conv.id, q_ana.id, q_luis.id


async def _cleanup(uid):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for model in (OwnerQuestion, Message, Conversation, Contact):
            await db.execute(delete(model).where(model.advertiser_id == uid))
        await db.execute(delete(User).where(User.id == uid))
        await db.commit()
    await engine.dispose()


async def _reply(uid, conv_id, text):
    request = MagicMock()
    request.headers = {}
    with (
        patch("app.services.realtime.publish_conversation_event", AsyncMock()),
        patch("app.workers.tasks.send_whatsapp_message") as task,
        patch("app.services.web_conversation.recently_on_web", AsyncMock(return_value=False)),
        patch("app.services.web_push.contacts_with_push", AsyncMock(return_value=[])),
    ):
        task.apply_async = MagicMock()
        async with AsyncSessionLocal() as db:
            user = await db.get(User, uid)
            return await reply_to_conversation(conv_id, request, ReplyBody(text=text), db=db,
                                               current_user=user, _=None, redis=None)


async def _status(qid):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(OwnerQuestion.status, OwnerQuestion.answer)
                                 .where(OwnerQuestion.id == qid))).one()


class TestInboxReplyClosesCentralQuestion:
    async def test_reply_closes_only_that_customers_pending_question(self):
        uid, conv_id, q_ana, q_luis = await _setup()
        try:
            out = await _reply(uid, conv_id, "Sí, fundas desde $120")
            assert out["message"] == "ok"
            assert tuple(await _status(q_ana)) == ("inbox", "Sí, fundas desde $120")
            # Otro cliente: su pregunta sigue esperando la respuesta del dueño.
            assert tuple(await _status(q_luis)) == ("pending", None)
        finally:
            await _cleanup(uid)

    async def test_owner_next_central_message_is_not_taken_as_the_answer(self):
        """Contestó a Ana en el Inbox; luego escribe al central algo sin citar:
        ya no hay pregunta de Ana pendiente, así que no se le manda nada a Ana."""
        uid, conv_id, _, q_luis = await _setup()
        try:
            await _reply(uid, conv_id, "Sí, fundas desde $120")
            async with AsyncSessionLocal() as db:
                user = await db.get(User, uid)
                user.whatsapp_number = OWNER_PHONE
                await db.execute(delete(OwnerQuestion).where(OwnerQuestion.id == q_luis))
                await db.commit()
            with (
                patch.object(svc, "send_platform_text", AsyncMock(return_value=("w", None))),
                patch.object(svc, "send_whatsapp", AsyncMock(return_value=("wamid.c", None))) as sw,
                patch.object(svc, "_answers_question", AsyncMock(return_value=True)),
                patch("app.services.copilot_whatsapp_service.handle_owner_command", AsyncMock()) as cmd,
                patch("app.services.copilot_whatsapp_service.has_open_builder", AsyncMock(return_value=False)),
            ):
                async with AsyncSessionLocal() as db:
                    await svc.handle_owner_message(db, from_number=OWNER_PHONE, text="sí tenemos de todas",
                                                   context_wamid=None)
            sw.assert_not_awaited()
            cmd.assert_awaited_once()  # va al Copiloto, como cualquier mensaje sin pregunta pendiente
        finally:
            await _cleanup(uid)

    async def test_quoting_an_inbox_answered_question_says_it_is_done(self):
        uid, conv_id, q_ana, _ = await _setup()
        try:
            await _reply(uid, conv_id, "Sí, fundas desde $120")
            async with AsyncSessionLocal() as db:
                user = await db.get(User, uid)
                user.whatsapp_number = OWNER_PHONE
                wamid = (await db.get(OwnerQuestion, q_ana)).owner_wamid
                await db.commit()
            with (
                patch.object(svc, "send_platform_text", AsyncMock(return_value=("w", None))) as sp,
                patch.object(svc, "send_whatsapp", AsyncMock(return_value=("wamid.c", None))) as sw,
                patch("app.services.copilot_whatsapp_service.handle_owner_command", AsyncMock()) as cmd,
            ):
                async with AsyncSessionLocal() as db:
                    await svc.handle_owner_message(db, from_number=OWNER_PHONE, text="sí hay",
                                                   context_wamid=wamid)
            sw.assert_not_awaited()
            cmd.assert_not_awaited()
            assert sp.call_args.args[1] == svc.ALREADY_ANSWERED_IN_INBOX
        finally:
            await _cleanup(uid)

    async def test_reply_without_pending_question_changes_nothing(self):
        uid, conv_id, _, _ = await _setup()
        try:
            async with AsyncSessionLocal() as db:
                await db.execute(delete(OwnerQuestion).where(OwnerQuestion.advertiser_id == uid))
                await db.commit()
            out = await _reply(uid, conv_id, "Hola Ana")
            assert out["message"] == "ok"
        finally:
            await _cleanup(uid)
