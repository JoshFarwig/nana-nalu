import logging

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies.core import get_async_db_session
from repositories.surf_spot_repository import AsyncSurfSpotRepository

logger = logging.getLogger(__name__)


def get_surf_spot_repository(
    session: AsyncSession = Depends(get_async_db_session),
) -> AsyncSurfSpotRepository:
    return AsyncSurfSpotRepository(session)
