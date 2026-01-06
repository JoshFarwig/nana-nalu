import logging

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import APISettings
from core.dependencies.core import get_async_db_session, get_settings
from repositories.account_tier_repository import AsyncAccountTierRepository
from repositories.surf_spot_repository import AsyncSurfSpotRepository
from repositories.user_repository import AsyncUserRepository

logger = logging.getLogger(__name__)


def get_user_repository(
    session: AsyncSession = Depends(get_async_db_session),
    settings: APISettings = Depends(get_settings),
) -> AsyncUserRepository:
    return AsyncUserRepository(session, settings)


def get_account_tier_repository(
    session: AsyncSession = Depends(get_async_db_session),
) -> AsyncAccountTierRepository:
    return AsyncAccountTierRepository(session)


def get_surf_spot_repository(
    session: AsyncSession = Depends(get_async_db_session),
) -> AsyncSurfSpotRepository:
    return AsyncSurfSpotRepository(session)
