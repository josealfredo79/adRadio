"""Tests for the kanban pipeline_stage feature on contacts."""
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import app.main as main_module
from app.api.deps import get_current_user
from app.database import get_db
from app.schemas.contact import ContactUpdate


@pytest.fixture
def client(test_user):
    async def _fake_user():
        return test_user

    main_module.app.dependency_overrides[get_current_user] = _fake_user
    yield TestClient(main_module.app)
    main_module.app.dependency_overrides.clear()


class TestContactUpdateSchemaValidation:
    def test_valid_stage_accepted(self):
        update = ContactUpdate(pipeline_stage="interesado")
        assert update.pipeline_stage == "interesado"

    def test_invalid_stage_rejected(self):
        with pytest.raises(ValueError):
            ContactUpdate(pipeline_stage="ganador")

    def test_none_is_allowed_unset(self):
        update = ContactUpdate()
        assert update.pipeline_stage is None


class TestPipelineEndpoint:
    def test_returns_only_active_contacts_for_current_user(self, client, test_user):
        c1 = MagicMock(
            id=uuid.uuid4(), phone="+521111111111", email=None, city=None,
            tags=[], language="es", status="active", engagement_score=10, source="manual",
            pipeline_stage="nuevo", last_interaction=None,
        )
        c1.name = "Juan"  # MagicMock(name=...) sets the mock's repr, not a .name attribute
        from datetime import datetime, timezone
        c1.created_at = datetime.now(timezone.utc)

        async def _fake_db():
            db = AsyncMock()
            result = MagicMock()
            result.scalars.return_value.all.return_value = [c1]
            db.execute.return_value = result
            yield db

        main_module.app.dependency_overrides[get_db] = _fake_db
        r = client.get("/api/v1/contacts/pipeline")

        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1
        assert data[0]["pipeline_stage"] == "nuevo"


class TestUpdateContactPipelineStage:
    def test_patch_contact_updates_stage(self, client, test_user):
        from datetime import datetime, timezone
        contact = MagicMock(
            id=uuid.uuid4(), advertiser_id=test_user.id, phone="+521111111111",
            email=None, city=None, tags=[], language="es", status="active", engagement_score=0,
            source="manual", pipeline_stage="nuevo", last_interaction=None,
            created_at=datetime.now(timezone.utc),
        )
        contact.name = "Ana"

        async def _fake_db():
            db = AsyncMock()
            result = MagicMock()
            result.scalar_one_or_none.return_value = contact
            db.execute.return_value = result
            yield db

        main_module.app.dependency_overrides[get_db] = _fake_db
        r = client.patch(f"/api/v1/contacts/{contact.id}", json={"pipeline_stage": "cliente"})

        assert r.status_code == 200
        assert contact.pipeline_stage == "cliente"

    def test_patch_rejects_invalid_stage(self, client, test_user):
        async def _fake_db():
            db = AsyncMock()
            yield db

        main_module.app.dependency_overrides[get_db] = _fake_db
        r = client.patch(f"/api/v1/contacts/{uuid.uuid4()}", json={"pipeline_stage": "no_existe"})

        assert r.status_code == 422
