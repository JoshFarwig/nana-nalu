import asyncio
import logging
from sqlalchemy import select, func
from core import AsyncDatabaseManager, BaseConfig, get_settings
from models.user_model import User
from models.surf_spot_model import SurfSpot
from repositories.user_repository import UserRepository
from scripts.seed.seed_factory import SeedFactory
from utils.location import get_location


class SeedManager:
    def __init__(self, settings: BaseConfig):
        self.settings = settings
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.db_manager = AsyncDatabaseManager(settings.db)

        # get location from envs
        self.location = get_location()

        self.logger.info(
            "SeedManager initialized",
            extra={
                "location": self.location.value,
            },
        )

    async def get_admin(self) -> User:
        """Get existing admin user or seed admin user and return reference."""

        async with self.db_manager.session_context() as session:
            user_repo = UserRepository(session, self.settings)

            # return existing admin or seed and return new admin user
            admin_user = await user_repo.get_by_username(
                self.settings.api.admin_username.get_secret_value()
            )

            if admin_user:
                self.logger.info(
                    "Found existing admin user",
                    extra={"id": admin_user.id},
                )
                return admin_user
            else:
                admin_user = await user_repo.add(
                    {
                        "username": self.settings.api.admin_username.get_secret_value(),
                        "email": self.settings.api.admin_email.get_secret_value(),
                        "password": self.settings.api.admin_password.get_secret_value(),
                        "first_name": "Admin",
                        "last_name": "Admin",
                    }
                )

                self.logger.info(
                    "Seeded admin user",
                    extra={"id": admin_user.id},
                )
                return admin_user

    async def seed_surf_spots(self, admin_user: User) -> None:
        """Seed initial surf spots based on location configuration."""

        async with self.db_manager.session_context() as session:
            # check if surf spots already exist using SQLAlchemy select
            result = await session.execute(select(func.count(SurfSpot.id)))
            count = result.scalar_one()

            if count > 0:
                self.logger.info("Surf spots already exist", extra={"count": count})
                return

            # get location-specific surf spots using factory
            try:
                surf_spots = SeedFactory.get_surf_spots(self.location, admin_user)
            except ValueError as e:
                self.logger.exception(
                    f"Failed to load seed data for location: {self.location.value}",
                    extra={"error": str(e)},
                )
                raise

            session.add_all(surf_spots)
            self.logger.info(
                f"Seeded {len(surf_spots)} surf spots for {self.location.value}",
                extra={
                    "count": len(surf_spots),
                    "location": self.location.value,
                    "created_by_id": admin_user.id,
                },
            )

    async def seed_database(self) -> None:
        """Main seeding method."""

        try:
            # get or seed admin user first, user required for surf spots
            admin_user = await self.get_admin()

            # seed surf spots
            await self.seed_surf_spots(admin_user)
        except Exception as e:
            self.logger.exception("Error seeding database", extra={"error": str(e)})
            raise
        finally:
            await self.db_manager.close()


async def main():
    """Run the seeder."""

    settings = get_settings()
    seeder = SeedManager(settings)
    await seeder.seed_database()


if __name__ == "__main__":
    asyncio.run(main())
