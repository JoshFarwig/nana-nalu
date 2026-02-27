import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from core.exceptions.account_tiers import AccountTierNotFoundError

from schemas.account_tier_schema import (
    AccountTierCreate,
    AccountTierUpdate,
)
from models.account_tier_model import AccountTier, DEFAULT_TIERS

logger = logging.getLogger(__name__)


class AsyncAccountTierRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, account_tier_id: int) -> AccountTier:
        result = await self.session.execute(
            select(AccountTier).where(AccountTier.id == account_tier_id)
        )

        account_tier = result.scalar_one_or_none()

        if account_tier is None:
            raise AccountTierNotFoundError(account_tier_id, "id")

        return account_tier

    async def get_by_name(self, name: str) -> AccountTier:
        """e.g., 'free', 'kokua'."""
        result = await self.session.execute(
            select(AccountTier).where(AccountTier.name == name)
        )

        account_tier = result.scalar_one_or_none()

        if account_tier is None:
            raise AccountTierNotFoundError(name, "name")

        return account_tier

    async def create(self, account_tier_data: AccountTierCreate) -> AccountTier:
        account_tier = AccountTier(**account_tier_data.model_dump())
        self.session.add(account_tier)
        return account_tier

    async def update(self, account_tier_id: int, account_tier_data: AccountTierUpdate):
        account_tier = await self.get_by_id(account_tier_id)

        for key, value in account_tier_data.model_dump().items():
            if hasattr(account_tier, key):
                setattr(account_tier, key, value)

        return account_tier


class SyncAccountTierRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_by_id(self, account_tier_id: int) -> AccountTier:
        """Get account tier by ID."""
        result = self.session.execute(
            select(AccountTier).where(AccountTier.id == account_tier_id)
        )

        account_tier = result.scalar_one_or_none()

        if account_tier is None:
            raise AccountTierNotFoundError(account_tier_id, "id")

        return account_tier

    def get_by_name(self, name: str) -> AccountTier:
        """e.g., 'free', 'kokua'."""
        result = self.session.execute(
            select(AccountTier).where(AccountTier.name == name)
        )

        account_tier = result.scalar_one_or_none()

        if account_tier is None:
            raise AccountTierNotFoundError(name, "name")

        return account_tier

    def create(self, account_tier_data: AccountTierCreate) -> AccountTier:
        account_tier = AccountTier(**account_tier_data.model_dump())
        self.session.add(account_tier)
        return account_tier

    def create_defaults(self):
        """Create default tiers for seeding."""
        defaults = set()

        for _, tier_data in DEFAULT_TIERS.items():
            account_tier = AccountTier(**tier_data)
            self.session.add(account_tier)
            self.session.flush()

            logger.info(
                f"Created tier {account_tier.name} with defaults configured in account_tier_model.py",
                extra={"id": account_tier.id, "is_active": account_tier.is_active},
            )

            defaults.add(account_tier)

        return defaults

    def update(self, account_tier_id: int, account_tier_data: AccountTierUpdate):
        account_tier = self.get_by_id(account_tier_id)

        for key, value in account_tier_data.model_dump().items():
            if hasattr(account_tier, key):
                setattr(account_tier, key, value)

        return account_tier
