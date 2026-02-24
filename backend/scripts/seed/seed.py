import logging

from core.config import APISettings, load_settings
from core.database import SyncDatabaseManager
from core.exceptions.users import UserNotFoundError

from repositories.account_tier_repository import SyncAccountTierRepository
from repositories.user_repository import SyncUserRepository
from repositories.surf_spot_repository import SyncSurfSpotRepository

# Removed schema imports - using dicts directly for seeding
from scripts.seed.seed_factory import SeedFactory

logger = logging.getLogger(__name__)


class SeedManager:
    def __init__(self, settings: APISettings):
        self.settings = settings
        self.db_manager = SyncDatabaseManager(settings.db)

    def seed_tiers(self) -> int:
        """Seed tiers and return the default tier ID"""
        with self.db_manager.auto_commit_session() as session:
            account_tier_repo = SyncAccountTierRepository(session)

            # Try to get existing free tier first
            try:
                free_tier = account_tier_repo.get_by_name("free")
                logger.info("Account tiers already exist, skipping creation")
                return free_tier.id
            except Exception:
                # Tiers don't exist, create them
                account_tier_repo.create_defaults()
                free_tier = account_tier_repo.get_by_name("free")
                return free_tier.id

    def seed_admin(self, free_tier_id: int) -> int:
        """Seed admin user and return ID."""

        with self.db_manager.auto_commit_session() as session:
            user_repo = SyncUserRepository(session, self.settings)

            try:
                admin_user = user_repo.get_by_username(
                    self.settings.api.admin_username.get_secret_value()
                )
                logger.info(
                    "Admin user already exists, skipping creation",
                    extra={"id": admin_user.id},
                )
                return admin_user.id

            except UserNotFoundError:
                admin_user = user_repo.create(
                    user_data={
                        "tier_id": free_tier_id,
                        "username": self.settings.api.admin_username.get_secret_value(),
                        "email": self.settings.api.admin_email.get_secret_value(),
                        "first_name": self.settings.api.admin_name,
                        "last_name": self.settings.api.admin_name,
                        "password": self.settings.api.admin_password.get_secret_value(),
                        "verified": True,
                        "is_admin": True,
                    }
                )
                session.flush()

                logger.info(
                    "Seeded admin user",
                    extra={"id": admin_user.id},
                )
                return admin_user.id

    def seed_demo_surf_spots(self, admin_user_id: int) -> None:
        """Seed initial demo surf spots based on enabled locations."""

        with self.db_manager.auto_commit_session() as session:
            surf_spot_repo = SyncSurfSpotRepository(session)

            if surf_spot_repo.any_exist():
                logger.warning("Surf spots already exist")
                return

            # get all demo surf spots for all enabled regions
            surf_spots = SeedFactory.get_all_demo_surf_spots(admin_user_id)

            if not surf_spots:
                logger.warning("No surf spots loaded from any enabled regions")
                return

            session.add_all(surf_spots)

            logger.info(
                f"Seeded {len(surf_spots)} surf spots across enabled regions",
                extra={
                    "count": len(surf_spots),
                    "created_by_id": admin_user_id,
                },
            )

    def seed_database(self) -> None:
        """Main seeding method, applies all seed methods defined"""

        try:
            free_tier_id = self.seed_tiers()
            admin_user_id = self.seed_admin(free_tier_id)
            self.seed_demo_surf_spots(admin_user_id)
        except Exception as e:
            logger.exception("Error seeding database", extra={"error": str(e)})
            raise
        finally:
            self.db_manager.close()


def main():
    """Run the seeder."""

    settings = load_settings("api")
    seeder = SeedManager(settings)
    seeder.seed_database()


if __name__ == "__main__":
    main()
