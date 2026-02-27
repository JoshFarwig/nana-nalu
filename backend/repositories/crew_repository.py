import logging
from collections.abc import Sequence
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from core.config import APISettings
from models.crew_model import Crew
from models.crew_member_model import CrewMember, CrewRole
from models.user_model import User
from schemas.crew_schema import CrewCreate, CrewUpdate


logger = logging.getLogger(__name__)


class AsyncCrewRepository:
    def __init__(
        self,
        session: AsyncSession,
        settings: APISettings,
    ):
        self.session = session
        self.settings = settings

    async def exists_by_id(self, crew_id: int) -> bool:
        """Check if crew exists by ID."""
        result = await self.session.execute(select(Crew.id).where(Crew.id == crew_id))
        return result.scalar_one_or_none() is not None

    async def get_by_id(self, crew_id: int) -> Crew | None:
        """Get crew by ID with SELECT FOR UPDATE lock (without relationships)."""
        result = await self.session.execute(select(Crew).where(Crew.id == crew_id))
        return result.scalar_one_or_none()

    async def get_by_id_with_lock(self, crew_id: int) -> Crew | None:
        """Get crew by ID (without relationships)."""
        result = await self.session.execute(
            select(Crew).where(Crew.id == crew_id).with_for_update()
        )
        return result.scalar_one_or_none()

    async def get_by_id_with_members(self, crew_id: int) -> Crew | None:
        """Get crew by ID with members eagerly loaded."""
        result = await self.session.execute(
            select(Crew)
            .where(Crew.id == crew_id)
            .options(
                selectinload(Crew.members).selectinload(CrewMember.user),
                selectinload(Crew.owner).selectinload(User.tier),
            )
        )
        return result.scalar_one_or_none()

    async def get_crews_for_user(self, user_id: int) -> Sequence[Crew]:
        """Get all crews a user is a member of."""
        result = await self.session.execute(
            select(Crew)
            .join(CrewMember)
            .where(CrewMember.user_id == user_id)
            .options(selectinload(Crew.owner).selectinload(User.tier))
        )
        return result.scalars().all()

    async def count_crews_for_user(self, user_id: int) -> int:
        """Count total crews user is a member of (for quota checking)."""
        result = await self.session.execute(
            select(func.count())
            .select_from(CrewMember)
            .where(CrewMember.user_id == user_id)
        )
        return result.scalar_one()

    async def count_members(self, crew_id: int) -> int:
        """Count members in a crew (for capacity checking)."""
        result = await self.session.execute(
            select(func.count())
            .select_from(CrewMember)
            .where(CrewMember.crew_id == crew_id)
        )
        return result.scalar_one()

    async def create(self, crew_data: dict) -> Crew:
        """Create a new crew - internal method."""
        crew = Crew(**crew_data)
        self.session.add(crew)
        return crew

    async def create_crew(self, owner_id: int, crew_data: CrewCreate) -> Crew:
        """Create a new crew from schema."""
        data = crew_data.model_dump()
        data["owner_id"] = owner_id
        return await self.create(data)

    async def update(self, crew_id: int, crew_data: dict) -> Crew | None:
        """Update crew by ID - internal method."""
        crew = await self.get_by_id(crew_id)
        if not crew:
            return None

        for key, value in crew_data.items():
            if hasattr(crew, key):
                setattr(crew, key, value)

        return crew

    async def update_crew(self, crew_id: int, crew_data: CrewUpdate) -> Crew | None:
        """Update crew from schema."""
        data = crew_data.model_dump(exclude_unset=True)
        return await self.update(crew_id, data)

    async def add_member(
        self, crew_id: int, user_id: int, role: CrewRole = "member"
    ) -> CrewMember:
        """Add a member to a crew."""
        member = CrewMember(crew_id=crew_id, user_id=user_id, role=role)
        self.session.add(member)
        return member

    async def remove_member(self, crew_id: int, user_id: int) -> bool:
        """Remove a member from a crew."""
        result = await self.session.execute(
            select(CrewMember).where(
                CrewMember.crew_id == crew_id,
                CrewMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()

        if member:
            await self.session.delete(member)
            return True
        return False

    async def get_membership(self, crew_id: int, user_id: int) -> CrewMember | None:
        """Get a specific crew membership."""
        result = await self.session.execute(
            select(CrewMember).where(
                CrewMember.crew_id == crew_id,
                CrewMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def is_member(self, crew_id: int, user_id: int) -> bool:
        """Check if user is a member of a crew."""
        membership = await self.get_membership(crew_id, user_id)
        return membership is not None

    async def get_newest_members(
        self, crew_id: int, count: int
    ) -> Sequence[CrewMember]:
        """
        Get the newest members of a crew (by join date).
        Used for LIFO removal during tier downgrades.
        """
        result = await self.session.execute(
            select(CrewMember)
            .where(CrewMember.crew_id == crew_id)
            .where(CrewMember.role != "owner")  # never remove owner
            .order_by(CrewMember.created_at.desc())
            .limit(count)
        )
        return result.scalars().all()

    async def delete(self, crew_id: int) -> bool:
        """Delete a crew by ID."""
        crew = await self.get_by_id(crew_id)
        if crew:
            await self.session.delete(crew)
            return True
        return False
