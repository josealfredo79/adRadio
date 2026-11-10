"""El bot aprende de lo que el dueño contesta en el Inbox — un test por caso de
docs/specs/2026-10-12-bot-aprende-del-inbox.md. BD real; solo la IA y los
embeddings (APIs de pago) se simulan."""
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select

from app.api.v1.conversations import (
    LearnBody,
    LearnSuggestionBody,
    learn_from_reply,
    learn_suggestion,
)
from app.database import AsyncSessionLocal, engine
from app.models.contact import Contact
from app.models.conversation import Conversation
from app.models.knowledge_base import KnowledgeBase
from app.models.message import Message
from app.models.owner_question import OwnerQuestion
from app.models.user import User
from app.services import inbox_learning
from app.services.owner_question_service import OWNER_ANSWERS_FILENAME
from app.services.rag_service import search_knowledge


def _vec(i: int) -> list[float]:
    """Vectores perpendiculares: mismo índice = mismo tema, distinto = nada que ver."""
    v = [0.0] * 1024
    v[i] = 1.0
    return v


ENVIOS, HORARIO = _vec(0), _vec(1)


async def _seed(question="¿hacen envíos?", owner_reply="Sí, enviamos a todo Tlaxiaco por $30", name="Ana López"):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Tacos Don Pepe")
        db.add(user)
        await db.flush()
        contact = Contact(advertiser_id=user.id, name=name, phone=f"+52155{uuid.uuid4().int % 10**8:08d}")
        db.add(contact)
        await db.flush()
        conv = Conversation(advertiser_id=user.id, contact_id=contact.id, messages=[])
        db.add(conv)
        now = datetime.now(timezone.utc)
        db.add(Message(advertiser_id=user.id, contact_id=contact.id, direction="inbound", content=question,
                       status="delivered", created_at=now - timedelta(minutes=2)))
        msg = Message(advertiser_id=user.id, contact_id=contact.id, direction="outbound", content=owner_reply,
                      status="sent", sender="owner", created_at=now)
        db.add(msg)
        await db.commit()
        return user.id, contact.id, conv.id, msg.id


async def _add_kb(user_id, chunk, embedding, filename=OWNER_ANSWERS_FILENAME):
    async with AsyncSessionLocal() as db:
        kb = KnowledgeBase(advertiser_id=user_id, filename=filename, file_type="txt", raw_text=chunk,
                           chunk_text=chunk, embedding=embedding, processing_status="done", is_active=True)
        db.add(kb)
        await db.commit()
        return kb.id


async def _cleanup(*user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        for uid in user_ids:
            for model in (OwnerQuestion, KnowledgeBase, Message, Conversation, Contact):
                await db.execute(delete(model).where(model.advertiser_id == uid))
            await db.execute(delete(User).where(User.id == uid))
        await db.commit()
    await engine.dispose()


def _ai(*replies):
    return patch.object(inbox_learning, "chat_completion", AsyncMock(side_effect=list(replies)))


USEFUL = json.dumps({"useful": True, "question": "¿Hacen envíos?", "answer": "Sí, a todo Tlaxiaco por $30."})


async def _suggest(user_id, conv_id, msg_id, *ai_replies, embedding=ENVIOS):
    with _ai(*ai_replies), patch.object(inbox_learning, "get_embedding", AsyncMock(return_value=embedding)):
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            out = await learn_suggestion(conv_id, LearnSuggestionBody(msg_id=msg_id), db=db, current_user=user)
    return out["suggestion"]


async def _save(user_id, conv_id, question, answer, replace_ids=()):
    with patch("app.services.owner_question_service.get_embedding", AsyncMock(return_value=ENVIOS)):
        async with AsyncSessionLocal() as db:
            user = await db.get(User, user_id)
            return await learn_from_reply(conv_id, LearnBody(question=question, answer=answer,
                                                             replace_ids=list(replace_ids)),
                                          db=db, current_user=user)


async def _owner_answers(user_id):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(KnowledgeBase).where(
            KnowledgeBase.advertiser_id == user_id, KnowledgeBase.filename == OWNER_ANSWERS_FILENAME,
        ))).scalars().all()


class TestBotLearnsFromInbox:
    @pytest.mark.asyncio
    async def test_caso1_business_info_gets_a_suggestion(self):
        user_id, _, conv_id, msg_id = await _seed()
        try:
            s = await _suggest(user_id, conv_id, msg_id, USEFUL)
            assert s == {"question": "¿Hacen envíos?", "answer": "Sí, a todo Tlaxiaco por $30.",
                         "replaces": [], "documents": []}
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso1_ai_sees_the_customer_question_and_owner_reply(self):
        user_id, _, conv_id, msg_id = await _seed()
        try:
            with _ai(USEFUL) as ai, patch.object(inbox_learning, "get_embedding", AsyncMock(return_value=ENVIOS)):
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    await learn_suggestion(conv_id, LearnSuggestionBody(msg_id=msg_id), db=db, current_user=user)
            prompt = ai.await_args_list[0].args[0][0]["content"]
            assert "Cliente: ¿hacen envíos?" in prompt and "Dueño: Sí, enviamos a todo Tlaxiaco por $30" in prompt
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso1_owner_answers_the_last_question_not_the_earlier_ones(self):
        """Prueba real CityCell 4-nov: el cliente preguntó por varios productos y al
        final '¿tiene micas?'; la tarjeta salió como '¿Qué productos venden?'."""
        user_id, contact_id, conv_id, msg_id = await _seed(question="¿tiene micas?", owner_reply="Sí, a $50")
        async with AsyncSessionLocal() as db:
            db.add(Message(advertiser_id=user_id, contact_id=contact_id, direction="inbound",
                           content="¿cuánto el Redmi Note 15?", status="delivered",
                           created_at=datetime.now(timezone.utc) - timedelta(minutes=5)))
            await db.commit()
        try:
            with _ai(USEFUL) as ai, patch.object(inbox_learning, "get_embedding", AsyncMock(return_value=ENVIOS)):
                async with AsyncSessionLocal() as db:
                    user = await db.get(User, user_id)
                    await learn_suggestion(conv_id, LearnSuggestionBody(msg_id=msg_id), db=db, current_user=user)
            prompt = ai.await_args_list[0].args[0][0]["content"]
            assert "Antes el cliente dijo:\n¿cuánto el Redmi Note 15?" in prompt
            assert "Cliente: ¿tiene micas?\nDueño: Sí, a $50" in prompt
            assert "LO MISMO que el cliente preguntó al final" in ai.await_args_list[0].kwargs["system"]
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso2_personal_reply_gets_no_suggestion(self):
        user_id, _, conv_id, msg_id = await _seed("¿ya viene mi pedido?", "Ya va en camino, 10 min")
        try:
            assert await _suggest(user_id, conv_id, msg_id, '{"useful": false}') is None
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso3_suggestion_with_customer_name_or_phone_is_dropped(self):
        user_id, _, conv_id, msg_id = await _seed()
        try:
            with_name = json.dumps({"useful": True, "question": "¿Hacen envíos?", "answer": "Sí Ana, $30."})
            assert await _suggest(user_id, conv_id, msg_id, with_name) is None
            async with AsyncSessionLocal() as db:
                phone = (await db.execute(select(Contact.phone).where(Contact.advertiser_id == user_id))).scalar_one()
            with_phone = json.dumps({"useful": True, "question": "¿Hacen envíos?", "answer": f"Sí, te marco al {phone[-10:]}"})
            assert await _suggest(user_id, conv_id, msg_id, with_phone) is None
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso3_placeholder_contact_name_does_not_block(self):
        user_id, _, conv_id, msg_id = await _seed(name="Cliente")
        try:
            useful = json.dumps({"useful": True, "question": "¿Atienden a cualquier cliente?", "answer": "Sí."})
            assert await _suggest(user_id, conv_id, msg_id, useful) is not None
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso4_saves_the_edited_text_and_the_bot_finds_it(self):
        user_id, _, conv_id, _ = await _seed()
        try:
            out = await _save(user_id, conv_id, "¿Hacen envíos?", "Sí, a todo Tlaxiaco por $35 (corregido).")
            assert out == {"saved": True, "replaced": 0, "reminder": ""}
            [kb] = await _owner_answers(user_id)
            assert kb.chunk_text == "Pregunta: ¿Hacen envíos?\nRespuesta: Sí, a todo Tlaxiaco por $35 (corregido)."
            assert kb.is_active
            with patch("app.services.rag_service.get_embedding", AsyncMock(return_value=ENVIOS)):
                async with AsyncSessionLocal() as db:
                    found = await search_knowledge(db, str(user_id), "¿mandan a domicilio?")
            assert "$35 (corregido)" in found
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso5_saying_no_saves_nothing(self):
        # "No" en la tarjeta no llama al servidor: con solo pedir la sugerencia no se guarda nada.
        user_id, _, conv_id, msg_id = await _seed()
        try:
            await _suggest(user_id, conv_id, msg_id, USEFUL)
            assert await _owner_answers(user_id) == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso6_contradicted_owner_answer_is_shown_and_replaced(self):
        user_id, _, conv_id, msg_id = await _seed()
        try:
            old_id = await _add_kb(user_id, "Pregunta: ¿Hacen envíos?\nRespuesta: Sí, $25.", ENVIOS)
            await _add_kb(user_id, "Pregunta: ¿Horario?\nRespuesta: 9 a 6.", HORARIO)  # otro tema
            s = await _suggest(user_id, conv_id, msg_id, USEFUL, '{"contradicts": [1]}')
            assert s["replaces"] == [{"id": str(old_id), "text": "Pregunta: ¿Hacen envíos?\nRespuesta: Sí, $25."}]
            out = await _save(user_id, conv_id, s["question"], s["answer"], [uuid.UUID(s["replaces"][0]["id"])])
            assert out["replaced"] == 1
            active = {kb.chunk_text: kb.is_active for kb in await _owner_answers(user_id)}
            assert active["Pregunta: ¿Hacen envíos?\nRespuesta: Sí, $25."] is False
            assert active["Pregunta: ¿Hacen envíos?\nRespuesta: Sí, a todo Tlaxiaco por $30."] is True
            assert active["Pregunta: ¿Horario?\nRespuesta: 9 a 6."] is True
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso6_same_topic_without_contradiction_replaces_nothing(self):
        user_id, _, conv_id, msg_id = await _seed()
        try:
            await _add_kb(user_id, "Pregunta: ¿Envían?\nRespuesta: Sí, a todo Tlaxiaco.", ENVIOS)
            s = await _suggest(user_id, conv_id, msg_id, USEFUL, '{"contradicts": []}')
            assert s["replaces"] == [] and s["documents"] == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso7_contradicted_document_is_warned_not_touched(self):
        user_id, _, conv_id, msg_id = await _seed()
        try:
            doc_id = await _add_kb(user_id, "MENÚ ... Envíos $25 ... Tacos $15 ...", ENVIOS, filename="menu.pdf")
            s = await _suggest(user_id, conv_id, msg_id, USEFUL, '{"contradicts": [1]}')
            assert s["replaces"] == [] and s["documents"] == ["menu.pdf"]
            # Aunque alguien mande su id, un documento nunca se desactiva por aquí.
            out = await _save(user_id, conv_id, s["question"], s["answer"], [doc_id])
            assert out["replaced"] == 0
            async with AsyncSessionLocal() as db:
                assert (await db.get(KnowledgeBase, doc_id)).is_active is True
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso8_ai_failure_means_no_card(self):
        user_id, _, conv_id, msg_id = await _seed()
        try:
            assert await _suggest(user_id, conv_id, msg_id, RuntimeError("proveedores caídos")) is None
            assert await _suggest(user_id, conv_id, msg_id, "no sé qué decir") is None
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso8_conflict_check_failure_still_suggests(self):
        user_id, _, conv_id, msg_id = await _seed()
        try:
            await _add_kb(user_id, "Pregunta: ¿Envían?\nRespuesta: $25", ENVIOS)
            s = await _suggest(user_id, conv_id, msg_id, USEFUL, RuntimeError("caído"))
            assert s["question"] == "¿Hacen envíos?" and s["replaces"] == []
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_caso9_other_business_cannot_suggest_or_replace(self):
        user_id, _, conv_id, msg_id = await _seed()
        other_id, _, other_conv_id, _ = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as e:
                    await learn_suggestion(conv_id, LearnSuggestionBody(msg_id=msg_id), db=db, current_user=other)
                assert e.value.status_code == 404
                # Su propia conversación, pero el mensaje de otro negocio.
                with pytest.raises(HTTPException) as e:
                    await learn_suggestion(other_conv_id, LearnSuggestionBody(msg_id=msg_id), db=db, current_user=other)
                assert e.value.status_code == 404
            victim_kb = await _add_kb(user_id, "Pregunta: ¿Envían?\nRespuesta: $25", ENVIOS)
            out = await _save(other_id, other_conv_id, "¿Hacen envíos?", "No.", [victim_kb])
            assert out["replaced"] == 0
            async with AsyncSessionLocal() as db:
                assert (await db.get(KnowledgeBase, victim_kb)).is_active is True
        finally:
            await _cleanup(user_id, other_id)

    @pytest.mark.asyncio
    async def test_caso9_only_owner_messages_can_be_learned(self):
        user_id, cid, conv_id, _ = await _seed()
        try:
            async with AsyncSessionLocal() as db:
                bot_msg = (await db.execute(select(Message).where(
                    Message.contact_id == cid, Message.direction == "inbound"))).scalar_one()
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException):
                    await learn_suggestion(conv_id, LearnSuggestionBody(msg_id=bot_msg.id), db=db, current_user=user)
        finally:
            await _cleanup(user_id)


# ─── Guardar en la tarjeta cierra la pregunta repetida del central (2026-11-10) ─
# Prueba real con CityCell: el cliente volvió a preguntar "¿Reparan pantallas??"
# justo después de que el dueño contestó en el Inbox; esa pregunta se quedaba
# pendiente en el central aunque el dueño luego tocó Guardar.

async def _pending(user_id, contact_id, question, minutes_ago=1, customer_wrote_after=False):
    async with AsyncSessionLocal() as db:
        contact = await db.get(Contact, contact_id)
        now = datetime.now(timezone.utc)
        oq = OwnerQuestion(advertiser_id=user_id, contact_id=contact_id, customer_phone=contact.phone,
                           question=question, created_at=now - timedelta(minutes=minutes_ago))
        db.add(oq)
        if customer_wrote_after:
            db.add(Message(advertiser_id=user_id, contact_id=contact_id, direction="inbound",
                           content="Reparan pantallas", status="delivered", created_at=now))
        await db.commit()
        return oq.id


async def _save_closing(user_id, conv_id, question, answer, verdict="SI", llm_error=False):
    llm = AsyncMock(side_effect=RuntimeError("caída")) if llm_error else AsyncMock(return_value=verdict)
    sent = AsyncMock(return_value=("wamid.X", None))
    with patch("app.services.owner_question_service.chat_completion", llm), \
         patch("app.services.owner_question_service.send_whatsapp", sent), \
         patch("app.services.owner_question_service._compose_customer_reply",
               AsyncMock(side_effect=lambda adv, q, a: a)), \
         patch("app.services.realtime.publish_conversation_event", AsyncMock()):
        out = await _save(user_id, conv_id, question, answer)
    return out, sent


async def _status(oq_id):
    async with AsyncSessionLocal() as db:
        return (await db.get(OwnerQuestion, oq_id)).status


async def _outbound(user_id, contact_id):
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(Message.content).where(
            Message.advertiser_id == user_id, Message.contact_id == contact_id,
            Message.direction == "outbound", Message.sender.is_(None),
        ))).scalars().all()


class TestSavingClosesRepeatedQuestion:
    @pytest.mark.asyncio
    async def test_matching_pending_question_is_closed_and_customer_gets_the_answer(self):
        user_id, contact_id, conv_id, _ = await _seed("¿Reparan pantallas?", "Si reparamos pantallas")
        try:
            oq = await _pending(user_id, contact_id, "Reparan pantallas??")
            out, sent = await _save_closing(user_id, conv_id, "¿Reparan pantallas?", "Sí, reparamos pantallas.")
            assert out["saved"] is True
            assert await _status(oq) == "inbox"
            sent.assert_awaited_once()
            assert sent.await_args.args[1] == "Sí, reparamos pantallas."
            assert await _outbound(user_id, contact_id) == ["Sí, reparamos pantallas."]
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_customer_wrote_again_closes_without_repeating(self):
        # Como en la prueba real: el cliente volvió a preguntar y el bot ya le contestó.
        user_id, contact_id, conv_id, _ = await _seed("¿Reparan pantallas?", "Si reparamos pantallas")
        try:
            oq = await _pending(user_id, contact_id, "Reparan pantallas??", customer_wrote_after=True)
            _, sent = await _save_closing(user_id, conv_id, "¿Reparan pantallas?", "Sí, reparamos pantallas.")
            assert await _status(oq) == "inbox"
            sent.assert_not_awaited()
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_other_question_stays_pending(self):
        user_id, contact_id, conv_id, _ = await _seed("¿Reparan pantallas?", "Si reparamos pantallas")
        try:
            oq = await _pending(user_id, contact_id, "¿Tienen micas?")
            _, sent = await _save_closing(user_id, conv_id, "¿Reparan pantallas?", "Sí, reparamos pantallas.",
                                          verdict="NO")
            assert await _status(oq) == "pending"
            sent.assert_not_awaited()
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_ai_failure_leaves_it_pending_and_still_saves(self):
        user_id, contact_id, conv_id, _ = await _seed("¿Reparan pantallas?", "Si reparamos pantallas")
        try:
            oq = await _pending(user_id, contact_id, "Reparan pantallas??")
            out, sent = await _save_closing(user_id, conv_id, "¿Reparan pantallas?", "Sí, reparamos pantallas.",
                                            llm_error=True)
            assert out["saved"] is True
            assert await _status(oq) == "pending"
            sent.assert_not_awaited()
            assert len(await _owner_answers(user_id)) == 1
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_old_question_outside_24h_is_closed_without_sending(self):
        # Fuera de la ventana sería una plantilla que Meta cobra.
        user_id, contact_id, conv_id, _ = await _seed("¿Reparan pantallas?", "Si reparamos pantallas")
        try:
            oq = await _pending(user_id, contact_id, "Reparan pantallas??", minutes_ago=24 * 60)
            _, sent = await _save_closing(user_id, conv_id, "¿Reparan pantallas?", "Sí, reparamos pantallas.")
            assert await _status(oq) == "inbox"
            sent.assert_not_awaited()
        finally:
            await _cleanup(user_id)

    @pytest.mark.asyncio
    async def test_other_customers_questions_are_not_touched(self):
        user_id, contact_id, conv_id, _ = await _seed("¿Reparan pantallas?", "Si reparamos pantallas")
        try:
            async with AsyncSessionLocal() as db:
                other = Contact(advertiser_id=user_id, name="Otro", phone="+5215511112222")
                db.add(other)
                await db.commit()
                other_id = other.id
            oq = await _pending(user_id, other_id, "Reparan pantallas??")
            _, sent = await _save_closing(user_id, conv_id, "¿Reparan pantallas?", "Sí, reparamos pantallas.")
            assert await _status(oq) == "pending"
            sent.assert_not_awaited()
        finally:
            await _cleanup(user_id)
