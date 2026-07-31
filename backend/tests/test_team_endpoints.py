"""Real-DB integration tests for team.py — zero coverage existed before
this file. Covers list/invite/update-role/remove ownership scoping, the
role whitelist (agent|viewer), and the duplicate-invite 409. Checked
`TeamMemberOut` against the `TeamMember` model for the str/UUID/datetime
response-typing bug seen in Admin/Public API/User Webhooks — already
correctly typed here (`id: UUID`, `invited_at`/`accepted_at: datetime`),
no bug found."""
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import delete

from app.api.v1.team import TeamMemberInvite, invite_member, list_team, remove_member, update_member_role
from app.database import AsyncSessionLocal, engine
from app.models.team_member import TeamMember
from app.models.user import User


async def _seed_user():
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        user = User(email=f"{uuid.uuid4()}@test.com", password_hash="x")
        db.add(user)
        await db.commit()
        return user.id


async def _cleanup(user_ids):
    await engine.dispose()
    async with AsyncSessionLocal() as db:
        await db.execute(delete(TeamMember).where(TeamMember.owner_id.in_(user_ids)))
        await db.execute(delete(User).where(User.id.in_(user_ids)))
        await db.commit()
    await engine.dispose()


class TestInviteMember:
    @pytest.mark.asyncio
    async def test_invites_with_default_role(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await invite_member(
                    body=TeamMemberInvite(email="colega@test.com"), db=db, current_user=user,
                )
            assert created.member_email == "colega@test.com"
            assert created.role == "agent"
            assert created.accepted_at is None
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_rejects_invalid_role(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await invite_member(
                        body=TeamMemberInvite(email="colega@test.com", role="admin"), db=db, current_user=user,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_duplicate_invite_returns_409(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await invite_member(body=TeamMemberInvite(email="colega@test.com"), db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await invite_member(body=TeamMemberInvite(email="colega@test.com"), db=db, current_user=user)
                assert exc_info.value.status_code == 409
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_same_email_allowed_for_different_owners(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                await invite_member(body=TeamMemberInvite(email="compartido@test.com"), db=db, current_user=owner)

            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                created = await invite_member(body=TeamMemberInvite(email="compartido@test.com"), db=db, current_user=other)
            assert created.member_email == "compartido@test.com"
        finally:
            await _cleanup([owner_id, other_id])


class TestListTeam:
    @pytest.mark.asyncio
    async def test_only_returns_own_members(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                await invite_member(body=TeamMemberInvite(email="mio@test.com"), db=db, current_user=owner)
                other = await db.get(User, other_id)
                await invite_member(body=TeamMemberInvite(email="ajeno@test.com"), db=db, current_user=other)

            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                members = await list_team(db=db, current_user=owner, page=1, page_size=20)
            assert [m.member_email for m in members] == ["mio@test.com"]
        finally:
            await _cleanup([owner_id, other_id])

    @pytest.mark.asyncio
    async def test_pagination_limits_page_size(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                for i in range(3):
                    await invite_member(body=TeamMemberInvite(email=f"m{i}@test.com"), db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                page1 = await list_team(db=db, current_user=user, page=1, page_size=2)
                page2 = await list_team(db=db, current_user=user, page=2, page_size=2)
            assert len(page1) == 2
            assert len(page2) == 1
        finally:
            await _cleanup([user_id])


class TestUpdateMemberRole:
    @pytest.mark.asyncio
    async def test_updates_role(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await invite_member(body=TeamMemberInvite(email="colega@test.com"), db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                updated = await update_member_role(
                    member_id=created.id, body=TeamMemberInvite(email="colega@test.com", role="viewer"),
                    db=db, current_user=user,
                )
            assert updated.role == "viewer"
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_rejects_invalid_role(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await invite_member(body=TeamMemberInvite(email="colega@test.com"), db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await update_member_role(
                        member_id=created.id, body=TeamMemberInvite(email="colega@test.com", role="admin"),
                        db=db, current_user=user,
                    )
                assert exc_info.value.status_code == 400
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unknown_member_returns_404(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await update_member_role(
                        member_id=uuid.uuid4(), body=TeamMemberInvite(email="x@test.com"), db=db, current_user=user,
                    )
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_cannot_update_another_owners_member(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                created = await invite_member(body=TeamMemberInvite(email="colega@test.com"), db=db, current_user=owner)

            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc_info:
                    await update_member_role(
                        member_id=created.id, body=TeamMemberInvite(email="colega@test.com", role="viewer"),
                        db=db, current_user=other,
                    )
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([owner_id, other_id])


class TestRemoveMember:
    @pytest.mark.asyncio
    async def test_removes_and_disappears_from_list(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                created = await invite_member(body=TeamMemberInvite(email="colega@test.com"), db=db, current_user=user)

            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                await remove_member(member_id=created.id, db=db, current_user=user)
                remaining = await list_team(db=db, current_user=user, page=1, page_size=20)
            assert remaining == []
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_unknown_member_returns_404(self):
        user_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                user = await db.get(User, user_id)
                with pytest.raises(HTTPException) as exc_info:
                    await remove_member(member_id=uuid.uuid4(), db=db, current_user=user)
                assert exc_info.value.status_code == 404
        finally:
            await _cleanup([user_id])

    @pytest.mark.asyncio
    async def test_cannot_remove_another_owners_member(self):
        owner_id = await _seed_user()
        other_id = await _seed_user()
        try:
            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                created = await invite_member(body=TeamMemberInvite(email="colega@test.com"), db=db, current_user=owner)

            async with AsyncSessionLocal() as db:
                other = await db.get(User, other_id)
                with pytest.raises(HTTPException) as exc_info:
                    await remove_member(member_id=created.id, db=db, current_user=other)
                assert exc_info.value.status_code == 404

            async with AsyncSessionLocal() as db:
                owner = await db.get(User, owner_id)
                remaining = await list_team(db=db, current_user=owner, page=1, page_size=20)
            assert len(remaining) == 1
        finally:
            await _cleanup([owner_id, other_id])
