from datetime import datetime
from collections.abc import Sequence

from sqlalchemy import Row, and_, func, select
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

    async def get_enabled_grids(
        self, provider: str, model: str
    ) -> Sequence[ModelRun]:
        """Latest run per region for provider/model. Used to advertise coverage on OOB errors."""
        latest = (
            select(
                ModelRun.region,
                func.max(ModelRun.run_time).label("latest_run_time"),
            )
            .where(ModelRun.provider == provider, ModelRun.model == model)
            .group_by(ModelRun.region)
            .subquery()
        )
        result = await self.session.execute(
            select(ModelRun)
            .join(
                latest,
                and_(
                    ModelRun.region == latest.c.region,
                    ModelRun.run_time == latest.c.latest_run_time,
                ),
            )
            .where(ModelRun.provider == provider, ModelRun.model == model)
        )
        return result.scalars().all()

    async def get_latest_for_point(
        self, provider: str, model: str, lat: float, lon: float
    ) -> ModelRun | None:
        """Latest run from any enabled region whose grid covers (lat, lon)."""
        result = await self.session.execute(
            select(ModelRun)
            .where(
                ModelRun.provider == provider,
                ModelRun.model == model,
                ModelRun.contains(lat, lon),
            )
            .order_by(ModelRun.run_time.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_distinct_combos(self) -> Sequence[ModelRun]:
        """
        Latest run per provider/model/region. Bounds + horizon read direct from columns.
        Used by /available to advertise coverage.
        """
        latest = (
            select(
                ModelRun.provider,
                ModelRun.model,
                ModelRun.region,
                func.max(ModelRun.run_time).label("latest_run_time"),
            )
            .group_by(ModelRun.provider, ModelRun.model, ModelRun.region)
            .subquery()
        )

        stmt = (
            select(ModelRun)
            .join(
                latest,
                and_(
                    ModelRun.provider == latest.c.provider,
                    ModelRun.model == latest.c.model,
                    ModelRun.region == latest.c.region,
                    ModelRun.run_time == latest.c.latest_run_time,
                ),
            )
            .order_by(ModelRun.provider, ModelRun.model, ModelRun.region)
        )
        result = await self.session.execute(stmt)
        return result.scalars().all()
