from datetime import datetime
from collections.abc import Sequence

from sqlalchemy import Row, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.model_run import ModelRun


class ModelRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_latest(
        self, provider: str, model: str, region: str
    ) -> ModelRun | None:
        result = await self.session.execute(
            select(ModelRun)
            .where(
                ModelRun.provider == provider,
                ModelRun.model == model,
                ModelRun.region == region,
            )
            .order_by(ModelRun.run_time.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_distinct_combos(self) -> Sequence:
        """
        Returns distinct provider/model/region combos with their latest run_time.
        Used for the /available endpoint to show what data is ingested.
        """
        result = await self.session.execute(
            select(
                ModelRun.provider,
                ModelRun.model,
                ModelRun.region,
                func.max(ModelRun.run_time).label("latest_run_time"),
            )
            .group_by(ModelRun.provider, ModelRun.model, ModelRun.region)
            .order_by(ModelRun.provider, ModelRun.model, ModelRun.region)
        )
        return result.fetchall()
