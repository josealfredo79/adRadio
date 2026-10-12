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
            for model in (KnowledgeBase, Message, Conversation, Contact):
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
            assert out == {"saved": True, "replaced": 0}
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
