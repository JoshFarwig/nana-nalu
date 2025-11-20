import logging
from core import SyncDatabaseManager, BaseConfig, get_settings
from models.user_model import User
from repositories import SyncUserRepository, SyncSurfSpotRepository
from scripts.seed.seed_factory import SeedFactory
from utils.location import get_location


class SeedManager:
    def __init__(self, settings: BaseConfig):
        self.settings = settings
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self.db_manager = SyncDatabaseManager(settings.db)

        self.location = get_location()

        self.logger.info(
            "SeedManager initialized",
            extra={
                "location": self.location.value,
            },
        )

    def get_admin(self) -> User:
        """Get existing admin user or seed admin user and return reference."""

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
                return admin_user
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
                return admin_user

    def seed_surf_spots(self, admin_user: User) -> None:
        """Seed initial surf spots based on location configuration."""

        with self.db_manager.auto_commit_session() as session:
            surf_spot_repo = SyncSurfSpotRepository(session)

            if surf_spot_repo.any_exist():
                self.logger.info("Surf spots already exist")
                return

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

    def seed_database(self) -> None:
        """Main seeding method."""

        try:
            # get or seed admin user first, user required for surf spots
            admin_user = self.get_admin()

            # seed surf spots
            self.seed_surf_spots(admin_user)
        except Exception as e:
            self.logger.exception("Error seeding database", extra={"error": str(e)})
            raise
        finally:
            self.db_manager.close()


def main():
    """Run the seeder."""

    settings = get_settings()
    seeder = SeedManager(settings)
    seeder.seed_database()


if __name__ == "__main__":
    main()
