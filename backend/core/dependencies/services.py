from fastapi import Depends

from core.config import APISettings
from core.dependencies.core import (
    get_async_http_manager,
    get_async_redis_manager,
    get_security_manager,
    get_settings,
    get_template_renderer,
)
from core.dependencies.repositories import (
    get_account_tier_repository,
    get_surf_spot_repository,
    get_user_repository,
)
from core.http import AsyncHTTPManager
from core.redis import AsyncRedisManager
from core.security import SecurityManager
from core.templates import TemplateRenderer
from repositories.account_tier_repository import AsyncAccountTierRepository
from repositories.surf_spot_repository import AsyncSurfSpotRepository
from repositories.user_repository import AsyncUserRepository

from services.email_service import EmailService
from services.magic_link_service import MagicLinkService
from services.auth_service import AuthService
from services.forecast.forecast_service import ForecastService


def get_email_service(
    http_manager: AsyncHTTPManager = Depends(get_async_http_manager),
    template_renderer: TemplateRenderer = Depends(get_template_renderer),
    settings: APISettings = Depends(get_settings),
) -> EmailService:
    return EmailService(http_manager, template_renderer, settings)


def get_magic_link_service(
    redis_manager: AsyncRedisManager = Depends(get_async_redis_manager),
    settings: APISettings = Depends(get_settings),
) -> MagicLinkService:
    return MagicLinkService(redis_manager, settings)


def get_auth_service(
    redis_manager: AsyncRedisManager = Depends(get_async_redis_manager),
    security_manager: SecurityManager = Depends(get_security_manager),
    email_service: EmailService = Depends(get_email_service),
    magic_link_service: MagicLinkService = Depends(get_magic_link_service),
    user_repo: AsyncUserRepository = Depends(get_user_repository),
    tier_repo: AsyncAccountTierRepository = Depends(get_account_tier_repository),
    settings: APISettings = Depends(get_settings),
) -> AuthService:
    return AuthService(
        redis_manager,
        security_manager,
        email_service,
        magic_link_service,
        user_repo,
        tier_repo,
        settings,
    )


def get_forecast_service(
    redis_manager: AsyncRedisManager = Depends(get_async_redis_manager),
    surf_spot_repo: AsyncSurfSpotRepository = Depends(get_surf_spot_repository),
) -> ForecastService:
    return ForecastService(redis_manager, surf_spot_repo)
