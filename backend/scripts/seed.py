import asyncio
import logging
from sqlalchemy import select, func
from geoalchemy2.elements import WKTElement
from core import AsyncDatabaseManager, BaseConfig, get_settings
from models.user_model import User
from models.surf_spot_model import SurfSpot
from repositories.user_repository import UserRepository


class SeedManager:
    def __init__(self, settings: BaseConfig):
        self.settings: BaseConfig = settings
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.db_manager = AsyncDatabaseManager(settings.db)

    async def get_admin(self) -> User:
        """Get existing admin user or seed admin user and return reference."""

        async with self.db_manager.session_context() as session:
            user_repo = UserRepository(session)

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
        """Seed initial surf spots."""

        async with self.db_manager.session_context() as session:
            # check if surf spots already exist using SQLAlchemy select
            result = await session.execute(select(func.count(SurfSpot.id)))
            count = result.scalar_one()

            if count > 0:
                self.logger.info("Surf spots already exist", extra={"count": count})
                return

            # seed surf spots (change at your preference / location)
            surf_spots = [
                SurfSpot(
                    name="Ho'okipa (Point)",
                    description="The iconic NSB grom-grounds (Point, Middles, Pavillions)",
                    location=WKTElement("POINT(-156.3596 20.9342)", srid=4326),
                    is_active=True,
                    created_by_id=admin_user.id,
                ),
                SurfSpot(
                    name="Honolua Bay (Coconuts)",
                    description="The legendary west-side point break",
                    location=WKTElement("POINT(-156.6410 21.0176)", srid=4326),
                    is_active=True,
                    created_by_id=admin_user.id,
                ),
                SurfSpot(
                    name="Olowalu",
                    description="West-side beach break",
                    location=WKTElement("POINT(-156.6309 20.8216)", srid=4326),
                    is_active=True,
                    created_by_id=admin_user.id,
                ),
                SurfSpot(
                    name="Hamoa beach",
                    description="Hana's day dream point and beach break (and sandbar one bay over)",
                    location=WKTElement("POINT(-155.9865 20.7184)", srid=4326),
                    is_active=True,
                    created_by_id=admin_user.id,
                ),
                SurfSpot(
                    name="Dumps",
                    description="Iconic south-side left (and right if you're nutz)",
                    location=WKTElement("POINT(-156.5480 20.6129)", srid=4326),
                    is_active=True,
                    created_by_id=admin_user.id,
                ),
                SurfSpot(
                    name="Shaws",
                    description="Reefy, super fun south-side left",
                    location=WKTElement("POINT(-156.4448 20.6734)", srid=4326),
                    is_active=True,
                    created_by_id=admin_user.id,
                ),
            ]

            session.add_all(surf_spots)
            self.logger.info(
                f"Seeded {len(surf_spots)} surf spots",
                extra={"count": len(surf_spots), "created_by_id": admin_user.id},
            )

    async def seed_database(self) -> None:
        """Main seeding method."""

        try:
            # get or seed admin user first, user required for surf spots
            admin_user = await self.get_admin()

            # seed surf spots
            await self.seed_surf_spots(admin_user)
        except Exception as e:
            self.logger.error(
                "Error seeding database", extra={"error": str(e)}, exc_info=True
            )
            raise
        finally:
            await self.db_manager.close()


async def main():
    """Run the seeder."""
    import os

    config = os.getenv("ENV", "dev")
    settings = get_settings(config)
    seeder = SeedManager(settings)
    await seeder.seed_database()


if __name__ == "__main__":
    asyncio.run(main())
