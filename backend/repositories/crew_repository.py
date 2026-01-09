from sqlalchemy.ext.asyncio import AsyncSession

from core.config import APISettings


from schemas.crew_schema import CrewCreate, CrewUpdate, CrewResponse


class AsyncCrewRepository:
    def __init__(
        self,
        session: AsyncSession,
        settings: APISettings,
    ):
        self.session = session
        self.settings = settings

    async def exists_by_id(self, crew_id: int):
        pass

    async def get_by_id(self, crew_id: int):
        pass

    async def create(self, crew_data: dict):
        pass

    async def create_crew(self, crew_data: CrewCreate):
        pass

    async def update(self, crew_data: dict):
        pass

    async def update_crew(self, crew_data: CrewUpdate):
        pass
