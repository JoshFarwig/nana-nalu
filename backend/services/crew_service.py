import logging

from sqlalchemy.ext.asyncio import AsyncSession

from core.config import APISettings
from core.exceptions.crews import (
    CrewNotFoundError,
    CrewQuotaExceededError,
    CrewFullError,
    AlreadyCrewMemberError,
    NotCrewMemberError,
    CrewPermissionError,
)

from models.crew_model import Crew
from models.crew_member_model import CrewMember

from repositories.crew_repository import AsyncCrewRepository
from repositories.surf_spot_repository import AsyncSurfSpotRepository
from repositories.user_repository import AsyncUserRepository

from schemas.crew_schema import CrewCreate

from services.magic_link_service import MagicLinkService


logger = logging.getLogger(__name__)


class CrewService:
    def __init__(
        self,
        crew_repo: AsyncCrewRepository,
        user_repo: AsyncUserRepository,
        spot_repo: AsyncSurfSpotRepository,
        magic_link_service: MagicLinkService,
        session: AsyncSession,
        settings: APISettings,
    ):
        self.crew_repo = crew_repo
        self.user_repo = user_repo
        self.spot_repo = spot_repo
        self.magic_link_service = magic_link_service
        self.session = session
        self.settings = settings.api

    async def _validate_user_crew_quota(self, user_id: int) -> None:
        """Check if user can join/create another crew based on their tier."""
        user = await self.user_repo.get_by_id_with_tier(user_id)
        current_count = await self.crew_repo.count_crews_for_user(user_id)
        max_allowed = user.tier.max_crews

        if current_count >= max_allowed:
            raise CrewQuotaExceededError(user_id, current_count, max_allowed)

    async def _validate_crew_capacity(self, crew: Crew) -> None:
        """Check if crew has room for another member."""
        current_count = await self.crew_repo.count_members(crew.id)
        max_members = crew.max_members

        if current_count >= max_members:
            raise CrewFullError(crew.id, current_count, max_members)

    async def _get_crew_or_raise(self, crew_id: int) -> Crew:
        """Get crew by ID or raise CrewNotFoundError."""
        crew = await self.crew_repo.get_by_id(crew_id)
        if not crew:
            raise CrewNotFoundError(crew_id)
        return crew

    async def _get_crew_with_lock_or_raise(self, crew_id: int) -> Crew:
        """Get crew by ID with a SELECT FOR UPDATE lock or raise CrewNotFoundError."""
        crew = await self.crew_repo.get_by_id_with_lock(crew_id)

        if crew is None:
            raise CrewNotFoundError(crew_id)
        return crew

    async def create_crew(self, owner_id: int, crew_data: CrewCreate) -> Crew:
        """Create a new crew with the user as owner."""
        await self._validate_user_crew_quota(owner_id)

        crew = await self.crew_repo.create_crew(owner_id, crew_data)
        await self.session.flush()

        await self.crew_repo.add_member(crew.id, owner_id, role="owner")
        await self.session.commit()

        logger.info(
            "Crew created",
            extra={"crew_id": crew.id, "owner_id": owner_id, "name": crew.name},
        )

        return crew

    async def join_crew(self, user_id: int, crew_id: int) -> CrewMember:
        """Join an existing crew (validates quota + capacity)."""
        crew = await self._get_crew_with_lock_or_raise(crew_id)

        if await self.crew_repo.is_member(crew_id, user_id):
            raise AlreadyCrewMemberError(user_id, crew_id)

        await self._validate_user_crew_quota(user_id)
        await self._validate_crew_capacity(crew)

        member = await self.crew_repo.add_member(crew_id, user_id, role="member")
        await self.session.commit()

        logger.info("User joined crew", extra={"user_id": user_id, "crew_id": crew_id})

        return member

    async def add_spot_to_crew(self, crew_id: int, spot_id: int):
        """Adds an existing spot to a crew, will shift spots into different crews as well"""
        spot = await self.spot_repo.get_by_id(spot_id)
        spot.crew_id = crew_id
        await self.session.commit()

        logger.info(
            "Added spot to crew", extra={"crew_id": crew_id, "spot_id": spot_id}
        )

    async def remove_spot_from_crew(self, crew_id: int, spot_id: int):
        """Removed a spot from a crew by unlinking the crew_id"""
        spot = await self.spot_repo.get_by_id(spot_id)
        spot.crew_id = None
        await self.session.commit()

        logger.info(
            "Removed spot from crew", extra={"crew_id": crew_id, "spot_id": spot_id}
        )

    async def remove_user_spots_from_crew(self, user_id: int, crew_id: int):
        """Remove all spots a user has registered in a crew"""
        spots = await self.spot_repo.get_all_user_spots_in_crew(crew_id, user_id)
        for spot in spots:
            spot.crew_id = None
        await self.session.commit()
        pass

    async def remove_user_from_crew(self, user_id: int, crew_id: int):
        """Remove a user from a crew and handle their allocated spots"""
        membership = await self.crew_repo.get_membership(crew_id, user_id)

        if not membership:
            raise NotCrewMemberError(user_id, crew_id)

        match membership.role:
            case "member":
                # remove remove user owned spots in crew, then remove user from crew
                spots = await self.spot_repo.get_all_user_spots_in_crew(
                    crew_id, user_id
                )
                for spot in spots:
                    spot.crew_id = None

                await self.crew_repo.remove_member(crew_id, user_id)

                await self.session.commit()

                logger.info(
                    "Member removed from crew",
                    extra={
                        "user_id": user_id,
                        "crew_id": crew_id,
                    },
                )

            case "owner":
                # TODO: decide on crew owner migration or removing crew and reallocating surf spots
                logger.info(
                    "Owner left crew, crew deleted",
                    extra={
                        "user_id": user_id,
                        "crew_id": crew_id,
                    },
                )
                return True

    async def get_crew(self, crew_id: int) -> Crew:
        """Get crew details with members."""
        return await self._get_crew_or_raise(crew_id)

    async def get_user_crews(self, user_id: int):
        """Get all crews a user is a member of."""
        return await self.crew_repo.get_crews_for_user(user_id)

    # =========================================================================
    # Magic Link Invite Methods
    # =========================================================================

    # TODO: generate_invite_link - create magic link for crew invites
    # TODO: accept_invite - consume magic link and join crew
    # TODO: preview_invite - validate link without consuming (for UI preview)
