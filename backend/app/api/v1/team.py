"""Team member management — /api/v1/team"""
from typing import List
from uuid import UUID
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.models.team_member import TeamMember
from app.models.user import User

router = APIRouter(prefix="/team", tags=["team"])


class TeamMemberInvite(BaseModel):
    email: EmailStr
    role: str = "agent"  # agent | viewer


class TeamMemberOut(BaseModel):
    id: UUID
    member_email: str
    role: str
    invited_at: datetime
    accepted_at: datetime | None

    class Config:
        from_attributes = True


@router.get("", response_model=List[TeamMemberOut])
async def list_team(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(TeamMember).where(TeamMember.owner_id == current_user.id).order_by(TeamMember.invited_at.desc())
    )
    return result.scalars().all()


@router.post("", response_model=TeamMemberOut, status_code=201)
async def invite_member(
    body: TeamMemberInvite,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if body.role not in ("agent", "viewer"):
        raise HTTPException(status_code=400, detail="role debe ser 'agent' o 'viewer'")

    # Prevent duplicate invites for the same email
    existing = await db.execute(
        select(TeamMember).where(
            TeamMember.owner_id == current_user.id,
            TeamMember.member_email == body.email,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Ya existe una invitación para ese email")

    member = TeamMember(
        owner_id=current_user.id,
        member_email=body.email,
        role=body.role,
    )
    db.add(member)
    await db.commit()
    await db.refresh(member)
    return member


@router.patch("/{member_id}", response_model=TeamMemberOut)
async def update_member_role(
    member_id: UUID,
    body: TeamMemberInvite,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(TeamMember).where(TeamMember.id == member_id, TeamMember.owner_id == current_user.id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")
    if body.role not in ("agent", "viewer"):
        raise HTTPException(status_code=400, detail="role debe ser 'agent' o 'viewer'")
    member.role = body.role
    await db.commit()
    await db.refresh(member)
    return member


@router.delete("/{member_id}", status_code=204)
async def remove_member(
    member_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(TeamMember).where(TeamMember.id == member_id, TeamMember.owner_id == current_user.id)
    )
    member = result.scalar_one_or_none()
    if not member:
        raise HTTPException(status_code=404, detail="Miembro no encontrado")
    await db.delete(member)
    await db.commit()
