"""Real-DB integration tests for automations.py — zero coverage existed
before this file. Covers flow CRUD/ownership scoping, the trigger
whitelist validation, toggle, and contact enrollment (including the
already-active-enrollment 409 and cross-tenant 404s on both the flow and
the contact side)."""
import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.api.v1.automations import (
    FlowCreate,
    StepIn,
    create_flow,
    delete_flow,
    enroll_contact,
    list_flows,
    toggle_flow,
)
from app.database import AsyncSessionLocal, engine
from app.models.automation import AutomationEnrollment, AutomationFlow
from app.models.contact import Contact
from app.models.user import User


async def _seed_user():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x")
        db.add(user)
        await db.commit()
        return user.id


async def _seed_contact(advertiser_id):
    async with AsyncSessionLocal() as db:
        contact = Contact(advertiser_id=advertiser_id, name="Cliente", phone=f"52155{uuid.uuid4().hex[:8]}")
        db.add(contact)
        await db.commit()
        return contact.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(AutomationEnrollment).where(AutomationEnrollment.advertiser_id.in_(user_ids)))
        await db.execute(delete(AutomationFlow).where(AutomationFlow.advertiser_id.in_(user_ids)))
        await db.execute(delete(Contact).where(Contact.advertiser_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestCreateFlow:
    @pytest.mark.asyncio
    async def test_creates_flow_with_steps(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_flow(
                    body=FlowCreate(
                        name="Bienvenida", trigger="new_contact",
                        steps=[StepIn(position=0, delay_minutes=5, message="Hola!")],
                    ),
                    db=db, current_user=user,
                )
            assert created.name == "Bienvenida"
            assert created.is_active is True
            assert len(created.steps) == 1
            assert created.steps[0].message == "Hola!"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_rejects_invalid_trigger(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await create_flow(
                        body=FlowCreate(name="Malo", trigger="not_a_real_trigger"),
                        db=db, current_user=user,
                    )
            assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])


class TestListFlows:
    @pytest.mark.asyncio
    async def test_only_returns_own_flows(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                await create_flow(body=FlowCreate(name="Mío"), db=db, current_user=owner)
                other = await db.get(User, other_id)
                await create_flow(body=FlowCreate(name="Ajeno"), db=db, current_user=other)

            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                flows = await list_flows(db=db, current_user=owner, page=1, page_size=20)
            assert [f.name for f in flows] == ["Mío"]
        finally:
            await _cleanup([owner_id, other_id])

    @pytest.mark.asyncio
    async def test_pagination_limits_page_size(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                for i in range(3):
                    await create_flow(body=FlowCreate(name=f"Flujo {i}"), db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                page1 = await list_flows(db=db, current_user=user, page=1, page_size=2)
                page2 = await list_flows(db=db, current_user=user, page=2, page_size=2)
            assert len(page1) == 2
            assert len(page2) == 1
        finally:
            await _cleanup([user_id])


class TestToggleFlow:
    @pytest.mark.asyncio
    async def test_toggles_active_state(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_flow(body=FlowCreate(name="Toggle"), db=db, current_user=user)
            assert created.is_active is True

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                toggled = await toggle_flow(flow_id=created.id, db=db, current_user=user)
            assert toggled.is_active is False

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                toggled_again = await toggle_flow(flow_id=created.id, db=db, current_user=user)
            assert toggled_again.is_active is True
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_cannot_toggle_another_advertisers_flow(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                created = await create_flow(body=FlowCreate(name="Owner's"), db=db, current_user=owner)

            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc_info:
                    await toggle_flow(flow_id=created.id, db=db, current_user=other)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([owner_id, other_id])


class TestDeleteFlow:
    @pytest.mark.asyncio
    async def test_deletes_and_disappears_from_list(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await create_flow(body=FlowCreate(name="Temp"), db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await delete_flow(flow_id=created.id, db=db, current_user=user)
                remaining = await list_flows(db=db, current_user=user, page=1, page_size=20)
            assert remaining == []
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unknown_flow_returns_404(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await delete_flow(flow_id=uuid.uuid4(), db=db, current_user=user)
            assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])


class TestEnrollContact:
    @pytest.mark.asyncio
    async def test_enrolls_and_computes_next_send_from_first_step_delay(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                flow = await create_flow(
                    body=FlowCreate(name="Con pasos", steps=[StepIn(position=0, delay_minutes=30, message="Hola")]),
                    db=db, current_user=user,
                )
            contact_id = await _seed_contact(user_id)

            before = datetime.now(timezone.utc)
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                result = await enroll_contact(flow_id=flow.id, contact_id=contact_id, db=db, current_user=user)
            assert result == {"enrolled": True}

            async with AsyncSessionLocal() as db:
                enr = (await db.execute(
                    delete(AutomationEnrollment).where(AutomationEnrollment.contact_id == contact_id).returning(AutomationEnrollment)
                )).scalar_one()
                await db.commit()
            assert enr.current_step == 0
            assert enr.next_send_at > before
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_duplicate_active_enrollment_returns_409(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                flow = await create_flow(body=FlowCreate(name="Flujo"), db=db, current_user=user)
            contact_id = await _seed_contact(user_id)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await enroll_contact(flow_id=flow.id, contact_id=contact_id, db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await enroll_contact(flow_id=flow.id, contact_id=contact_id, db=db, current_user=user)
                assert exc_info.value.status_code == 409
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unknown_flow_returns_404(self):
        user_id = await _seed_user()
        try:
            contact_id = await _seed_contact(user_id)
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await enroll_contact(flow_id=uuid.uuid4(), contact_id=contact_id, db=db, current_user=user)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unknown_contact_returns_404(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                flow = await create_flow(body=FlowCreate(name="Flujo"), db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await enroll_contact(flow_id=flow.id, contact_id=uuid.uuid4(), db=db, current_user=user)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_cannot_enroll_into_another_advertisers_flow(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                flow = await create_flow(body=FlowCreate(name="Owner's"), db=db, current_user=owner)
            other_contact_id = await _seed_contact(other_id)

            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc_info:
                    await enroll_contact(flow_id=flow.id, contact_id=other_contact_id, db=db, current_user=other)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([owner_id, other_id])

    @pytest.mark.asyncio
    async def test_enrolling_with_no_steps_leaves_next_send_none(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                flow = await create_flow(body=FlowCreate(name="Sin pasos"), db=db, current_user=user)
            contact_id = await _seed_contact(user_id)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await enroll_contact(flow_id=flow.id, contact_id=contact_id, db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                enr = (await db.execute(
                    delete(AutomationEnrollment).where(AutomationEnrollment.contact_id == contact_id).returning(AutomationEnrollment)
                )).scalar_one()
                await db.commit()
            assert enr.next_send_at is None
        finally:
            await _cleanup([user_id])
