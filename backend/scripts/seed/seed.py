import logging
from core.config import BaseConfig, load_settings
from core.database import SyncDatabaseManager
from models.user_model import User
from repositories.user_repository import SyncUserRepository
from repositories.surf_spot_repository import SyncSurfSpotRepository
from scripts.seed.seed_factory import SeedFactory
from utils.location import load_locations


class SeedManager:
    def __init__(self, settings: BaseConfig):
        self.settings = settings
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.db_manager = SyncDatabaseManager(settings.db)

        self.logger.info("SeedManager initialized")

    def get_or_seed_admin(self) -> int:
        """Get existing admin user or seed admin user and return ID."""

        with self.db_manager.auto_commit_session() as session:
            user_repo = SyncUserRepository(session, self.settings)

            # return existing admin or seed and return new admin user
            admin_user = user_repo.get_by_username(
                self.settings.api.admin_username.get_secret_value()
            )

            if admin_user:
                self.logger.info(
                    "Found existing admin user",
                    extra={"id": admin_user.id},
                )
                return admin_user.id
            else:
                admin_user = user_repo.add(
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
                return admin_user.id

    def seed_surf_spots(self, admin_user_id: int) -> None:
        """Seed initial surf spots based on enabled locations."""

        with self.db_manager.auto_commit_session() as session:
            surf_spot_repo = SyncSurfSpotRepository(session)

            if surf_spot_repo.any_exist():
                self.logger.info("Surf spots already exist")
                return

            # Get all surf spots for all enabled locations
            surf_spots = SeedFactory.get_all_surf_spots(admin_user_id)

            if not surf_spots:
                self.logger.warning("No surf spots loaded from any enabled location")
                return

            session.add_all(surf_spots)

            self.logger.info(
                f"Seeded {len(surf_spots)} surf spots across enabled locations",
                extra={
                    "count": len(surf_spots),
                    "created_by_id": admin_user_id,
                },
            )

    def seed_database(self) -> None:
        """Main seeding method."""

        try:
            admin_user_id = self.get_or_seed_admin()
            self.seed_surf_spots(admin_user_id)
        except Exception as e:
            self.logger.exception("Error seeding database", extra={"error": str(e)})
            raise
        finally:
            self.db_manager.close()


def main():
    """Run the seeder."""

    settings = load_settings()
    seeder = SeedManager(settings)
    seeder.seed_database()


if __name__ == "__main__":
    main()
