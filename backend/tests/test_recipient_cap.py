"""Tests for the messaging_limit_tier cap enforcement (Capa 10 anti-baneo)
— hace cumplir el tope oficial de Meta de destinatarios únicos con una
ventana de conversación NUEVA por ventana móvil de 24h. Complementa la
capa 8 (que solo ajusta el ritmo por hora vía quality_rating) haciendo
cumplir el tope de volumen real que Meta ya expone en messaging_limit_tier
pero que antes se guardaba sin usarse."""
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.meta_quality_service import resolve_tier_limit, _DEFAULT_TIER_LIMIT
from app.workers.task_helpers.campaign_ops import (
    RecipientCapState,
    _offer_or_queue,
    get_recipient_cap_state,
)


class TestResolveTierLimit:
    def test_known_tiers_map_correctly(self):
        assert resolve_tier_limit("TIER_250") == 250
        assert resolve_tier_limit("TIER_1K") == 1_000
        assert resolve_tier_limit("TIER_10K") == 10_000

    def test_unlimited_tier_has_no_cap(self):
        assert resolve_tier_limit("TIER_UNLIMITED") is None

    def test_none_falls_back_to_default(self):
        assert resolve_tier_limit(None) == _DEFAULT_TIER_LIMIT

    def test_unrecognized_tier_falls_back_to_default_and_logs_warning(self, caplog):
        with caplog.at_level("WARNING"):
            limit = resolve_tier_limit("TIER_DESCONOCIDO_FUTURO")
        assert limit == _DEFAULT_TIER_LIMIT
        assert "messaging_limit_tier desconocido" in caplog.text


class TestGetRecipientCapState:
    @pytest.mark.asyncio
    async def test_no_prior_sends_count_is_zero(self):
        from app.database import AsyncSessionLocal, engine
        from app.models.user import User
        await engine.dispose()

        async with AsyncSessionLocal() as db:
            advertiser = User(
                email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                meta_messaging_tier="TIER_250",
            )
            db.add(advertiser)
            await db.flush()
            await db.commit()

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser.id)
            state = await get_recipient_cap_state(db, advertiser)

        assert state.count == 0
        assert state.limit == 250

    @pytest.mark.asyncio
    async def test_only_counts_sends_within_rolling_24h_window(self):
        from app.database import AsyncSessionLocal, engine
        from app.models.contact import Contact
        from app.models.recipient_send import RecipientSend
        from app.models.user import User
        await engine.dispose()

        async with AsyncSessionLocal() as db:
            advertiser = User(
                email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                meta_messaging_tier="TIER_250",
            )
            db.add(advertiser)
            await db.flush()

            old_contact = Contact(advertiser_id=advertiser.id, phone="+5215500000001", name="Viejo", status="active")
            recent_contact = Contact(advertiser_id=advertiser.id, phone="+5215500000002", name="Reciente", status="active")
            db.add_all([old_contact, recent_contact])
            await db.flush()

            now = datetime.now(timezone.utc)
            db.add(RecipientSend(advertiser_id=advertiser.id, contact_id=old_contact.id, sent_at=now - timedelta(hours=30)))
            db.add(RecipientSend(advertiser_id=advertiser.id, contact_id=recent_contact.id, sent_at=now - timedelta(hours=2)))
            await db.commit()
            advertiser_id = advertiser.id

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            state = await get_recipient_cap_state(db, advertiser)

        assert state.count == 1  # solo el envío reciente cuenta

    @pytest.mark.asyncio
    async def test_same_contact_counted_once_even_with_multiple_windows(self):
        from app.database import AsyncSessionLocal, engine
        from app.models.contact import Contact
        from app.models.recipient_send import RecipientSend
        from app.models.user import User
        await engine.dispose()

        async with AsyncSessionLocal() as db:
            advertiser = User(
                email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                meta_messaging_tier="TIER_250",
            )
            db.add(advertiser)
            await db.flush()

            contact = Contact(advertiser_id=advertiser.id, phone="+5215500000003", name="Repetido", status="active")
            db.add(contact)
            await db.flush()

            now = datetime.now(timezone.utc)
            db.add(RecipientSend(advertiser_id=advertiser.id, contact_id=contact.id, sent_at=now - timedelta(hours=10)))
            db.add(RecipientSend(advertiser_id=advertiser.id, contact_id=contact.id, sent_at=now - timedelta(hours=5)))
            await db.commit()
            advertiser_id = advertiser.id

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            state = await get_recipient_cap_state(db, advertiser)

        assert state.count == 1  # COUNT(DISTINCT contact_id), no 2

    @pytest.mark.asyncio
    async def test_null_tier_uses_default_limit(self):
        from app.database import AsyncSessionLocal, engine
        from app.models.user import User
        await engine.dispose()

        async with AsyncSessionLocal() as db:
            advertiser = User(
                email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                meta_messaging_tier=None,
            )
            db.add(advertiser)
            await db.flush()
            await db.commit()
            advertiser_id = advertiser.id

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            state = await get_recipient_cap_state(db, advertiser)

        assert state.limit == _DEFAULT_TIER_LIMIT


class TestOfferOrQueueRespectsCap:
    """Usa un db completamente mockeado (como test_meta_quality_service.py)
    para aislar la lógica de _offer_or_queue de la capa 10 sin tocar una
    base de datos real."""

    def _advertiser(self, template_name="utility_template"):
        adv = MagicMock()
        adv.id = uuid.uuid4()
        adv.meta_utility_template_name = template_name
        adv.meta_radio_invite_template_name = None
        adv.business_name = "Test Business"
        return adv

    def _contact(self, consent="confirmed"):
        c = MagicMock()
        c.id = uuid.uuid4()
        c.phone = "+5215500000000"
        c.name = "Cliente"
        c.consent_status = consent
        return c

    @pytest.mark.asyncio
    async def test_open_window_bypasses_cap_entirely(self):
        """Ventana ya abierta: no consulta _cap ni escribe RecipientSend —
        re-enganchar no debe contar contra el tope."""
        db = AsyncMock()
        advertiser = self._advertiser()
        contact = self._contact()
        cap = RecipientCapState(limit=1, count=1)  # ya en el tope

        open_conv = MagicMock()
        with patch("app.services.whatsapp_window.is_window_open", return_value=True):
            outcome, _detail = await _offer_or_queue(
                db, advertiser, contact, _convs={str(contact.id): open_conv}, _cap=cap,
            )

        assert outcome == "open"
        assert cap.count == 1  # sin cambios
        db.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_new_window_under_cap_succeeds_and_records(self):
        db = AsyncMock()
        advertiser = self._advertiser()
        contact = self._contact()
        cap = RecipientCapState(limit=10, count=3)

        with patch("app.services.whatsapp_window.is_window_open", return_value=False), \
             patch("app.services.meta_service.send_whatsapp_template", new=AsyncMock(return_value=("sid-123", None))):
            outcome, _detail = await _offer_or_queue(
                db, advertiser, contact, _convs={}, _cap=cap,
            )

        assert outcome == "invited"
        assert cap.count == 4  # incrementado
        # db.add se llama varias veces en este flujo (Message de la plantilla,
        # RecipientSend de capa 10, Conversation nuevo) — aquí solo se verifica
        # que el RecipientSend del tier se agrega UNA vez, sin doble-conteo.
        from app.models.recipient_send import RecipientSend
        recipient_send_calls = [
            call for call in db.add.call_args_list if isinstance(call.args[0], RecipientSend)
        ]
        assert len(recipient_send_calls) == 1
        assert recipient_send_calls[0].args[0].contact_id == contact.id

    @pytest.mark.asyncio
    async def test_new_window_at_cap_is_blocked(self):
        db = AsyncMock()
        advertiser = self._advertiser()
        contact = self._contact()
        cap = RecipientCapState(limit=5, count=5)  # exactamente en el tope

        with patch("app.services.whatsapp_window.is_window_open", return_value=False), \
             patch("app.services.meta_service.send_whatsapp_template", new=AsyncMock()) as mock_send:
            outcome, _detail = await _offer_or_queue(
                db, advertiser, contact, _convs={}, _cap=cap,
            )

        assert outcome == "blocked"
        assert cap.count == 5  # sin cambios
        mock_send.assert_not_called()  # nunca intenta la plantilla
        # db.add IS called once now — to record the block in send_block_logs
        # (built 2026-08-13) — but nothing else (no RecipientSend/Conversation).
        db.add.assert_called_once()
        from app.models.send_block_log import REASON_RECIPIENT_CAP
        logged = db.add.call_args.args[0]
        assert logged.reason == REASON_RECIPIENT_CAP

    @pytest.mark.asyncio
    async def test_unlimited_tier_never_blocks(self):
        db = AsyncMock()
        advertiser = self._advertiser()
        contact = self._contact()
        cap = RecipientCapState(limit=None, count=999_999)  # TIER_UNLIMITED

        with patch("app.services.whatsapp_window.is_window_open", return_value=False), \
             patch("app.services.meta_service.send_whatsapp_template", new=AsyncMock(return_value=("sid-123", None))):
            outcome, _detail = await _offer_or_queue(
                db, advertiser, contact, _convs={}, _cap=cap,
            )

        assert outcome == "invited"


class TestScheduleCampaignRespectsRecipientCap:
    def test_advertiser_already_at_tier_cap_gets_paused_without_sending(self):
        """Real DB end-to-end, mismo patrón que
        TestScheduleCampaignRespectsSegmentCooldown en test_segment_cooldown.py:
        schedule_campaign corre su propio asyncio.run() interno, así que
        seed/check deben quedarse síncronos vía asyncio.run() por separado."""
        import asyncio

        from app.database import AsyncSessionLocal, engine
        from app.models.campaign import Campaign
        from app.models.contact import Contact
        from app.models.recipient_send import RecipientSend
        from app.models.user import User
        from app.workers.tasks import schedule_campaign

        async def _seed():
            await engine.dispose()
            async with AsyncSessionLocal() as db:
                advertiser = User(
                    email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                    messages_remaining=1000, meta_messaging_tier="TIER_50",
                )
                db.add(advertiser)
                await db.flush()

                # Sembrar 50 destinatarios únicos ya enganchados en las
                # últimas 24h — TIER_50 ya está al tope.
                now = datetime.now(timezone.utc)
                for i in range(50):
                    c = Contact(
                        advertiser_id=advertiser.id, phone=f"+521550000{i:04d}",
                        name=f"Previo {i}", status="active",
                    )
                    db.add(c)
                    await db.flush()
                    db.add(RecipientSend(advertiser_id=advertiser.id, contact_id=c.id, sent_at=now - timedelta(hours=1)))

                target_contact = Contact(
                    advertiser_id=advertiser.id, phone="+5215599999999",
                    name="Nuevo objetivo", status="active",
                )
                db.add(target_contact)

                campaign = Campaign(
                    advertiser_id=advertiser.id, name="Promo tope alcanzado", type="promo",
                    message_text="hola", status="scheduled", segment={"tags": ["nueva-lista"]},
                )
                db.add(campaign)
                await db.commit()
                return campaign.id

        campaign_id = asyncio.run(_seed())

        with patch("app.services.messaging_throttle.is_human_hour", return_value=True), \
             patch("app.workers.tasks.send_regular_messages", new=AsyncMock()) as mock_send:
            schedule_campaign(str(campaign_id))
            mock_send.assert_not_awaited()

        async def _check():
            await engine.dispose()
            async with AsyncSessionLocal() as db:
                c = await db.get(Campaign, campaign_id)
                return c.status

        assert asyncio.run(_check()) == "paused"
