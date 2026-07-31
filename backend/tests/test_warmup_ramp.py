"""Tests for the new-number warm-up ramp (Capa 11 anti-baneo) — reduce el
tope de destinatarios únicos/24h por debajo del messaging_limit_tier de Meta
mientras el número recién conectado sigue siendo nuevo."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services.meta_quality_service import resolve_warmup_cap


class TestResolveWarmupCap:
    def test_no_connected_at_means_no_restriction(self):
        """Números conectados antes de que existiera esta columna (o
        cualquier caso donde no se conozca la fecha) no se restringen
        retroactivamente."""
        assert resolve_warmup_cap(None) is None

    def test_just_connected_gets_strictest_cap(self):
        now = datetime.now(timezone.utc)
        assert resolve_warmup_cap(now) == 20

    def test_day_5_gets_second_tier_cap(self):
        connected_at = datetime.now(timezone.utc) - timedelta(days=5)
        assert resolve_warmup_cap(connected_at) == 50

    def test_day_10_gets_third_tier_cap(self):
        connected_at = datetime.now(timezone.utc) - timedelta(days=10)
        assert resolve_warmup_cap(connected_at) == 150

    def test_day_20_gets_fourth_tier_cap(self):
        connected_at = datetime.now(timezone.utc) - timedelta(days=20)
        assert resolve_warmup_cap(connected_at) == 500

    def test_past_ramp_has_no_extra_cap(self):
        connected_at = datetime.now(timezone.utc) - timedelta(days=45)
        assert resolve_warmup_cap(connected_at) is None


class TestGetRecipientCapStateCombinesWarmupAndTier:
    @pytest.mark.asyncio
    async def test_warmup_cap_overrides_looser_tier_limit(self):
        """Número recién conectado con TIER_1K (1000) — la rampa de warm-up
        (20) debe ganar por ser más estricta."""
        from app.database import AsyncSessionLocal, engine
        from app.models.user import User
        from app.workers.task_helpers.campaign_ops import get_recipient_cap_state
        await engine.dispose()

        async with AsyncSessionLocal() as db:
            advertiser = User(
                email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                meta_messaging_tier="TIER_1K",
                meta_connected_at=datetime.now(timezone.utc),
            )
            db.add(advertiser)
            await db.flush()
            await db.commit()
            advertiser_id = advertiser.id

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            state = await get_recipient_cap_state(db, advertiser)

        assert state.limit == 20

    @pytest.mark.asyncio
    async def test_tier_limit_overrides_looser_warmup_cap(self):
        """Número a mitad de rampa (tope de warm-up 150) pero con un tier ya
        muy estricto (TIER_50) — el tier debe ganar por ser más estricto."""
        from app.database import AsyncSessionLocal, engine
        from app.models.user import User
        from app.workers.task_helpers.campaign_ops import get_recipient_cap_state
        await engine.dispose()

        async with AsyncSessionLocal() as db:
            advertiser = User(
                email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                meta_messaging_tier="TIER_50",
                meta_connected_at=datetime.now(timezone.utc) - timedelta(days=10),
            )
            db.add(advertiser)
            await db.flush()
            await db.commit()
            advertiser_id = advertiser.id

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            state = await get_recipient_cap_state(db, advertiser)

        assert state.limit == 50

    @pytest.mark.asyncio
    async def test_unlimited_tier_still_bounded_by_warmup(self):
        """TIER_UNLIMITED (None) no debe anular la rampa de warm-up mientras
        el número sigue siendo nuevo."""
        from app.database import AsyncSessionLocal, engine
        from app.models.user import User
        from app.workers.task_helpers.campaign_ops import get_recipient_cap_state
        await engine.dispose()

        async with AsyncSessionLocal() as db:
            advertiser = User(
                email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                meta_messaging_tier="TIER_UNLIMITED",
                meta_connected_at=datetime.now(timezone.utc),
            )
            db.add(advertiser)
            await db.flush()
            await db.commit()
            advertiser_id = advertiser.id

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            state = await get_recipient_cap_state(db, advertiser)

        assert state.limit == 20

    @pytest.mark.asyncio
    async def test_old_number_only_bounded_by_tier(self):
        """Número conectado hace mucho — sin restricción extra de warm-up,
        solo aplica el tope del messaging_limit_tier."""
        from app.database import AsyncSessionLocal, engine
        from app.models.user import User
        from app.workers.task_helpers.campaign_ops import get_recipient_cap_state
        await engine.dispose()

        async with AsyncSessionLocal() as db:
            advertiser = User(
                email=f"{uuid.uuid4()}@test.com", password_hash="x", business_name="Test",
                meta_messaging_tier="TIER_250",
                meta_connected_at=datetime.now(timezone.utc) - timedelta(days=90),
            )
            db.add(advertiser)
            await db.flush()
            await db.commit()
            advertiser_id = advertiser.id

        async with AsyncSessionLocal() as db:
            advertiser = await db.get(User, advertiser_id)
            state = await get_recipient_cap_state(db, advertiser)

        assert state.limit == 250
