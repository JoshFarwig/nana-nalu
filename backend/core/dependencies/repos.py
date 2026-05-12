from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.dependencies.core import get_async_db_session
from repositories.model_run_repository import ModelRunRepository


def get_model_run_repo(
    session: AsyncSession = Depends(get_async_db_session),
) -> ModelRunRepository:
    return ModelRunRepository(session)
