from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import APISettings
from core.dependencies.core import (
    get_async_db_session,
    get_async_http_manager,
    get_async_redis_manager,
    get_security_manager,
    get_settings,
    get_template_renderer,
)
from core.dependencies.repositories import (
    get_account_tier_repository,
    get_condition_profile_repository,
    get_crew_repository,
    get_surf_spot_repository,
    get_user_repository,
)
from core.http import AsyncHTTPManager
from core.redis import AsyncRedisManager
from core.security import SecurityManager
from core.templates import TemplateRenderer
from repositories.account_tier_repository import AsyncAccountTierRepository
from repositories.condition_profile_repository import AsyncConditionProfileRepository
from repositories.crew_repository import AsyncCrewRepository
from repositories.surf_spot_repository import AsyncSurfSpotRepository
from repositories.user_repository import AsyncUserRepository

from services.auth_service import AuthService
from services.condition_profile_service import ConditionProfileService
from services.crew_service import CrewService
from services.email_service import EmailService
from services.forecast.forecast_service import ForecastService
from services.magic_link_service import MagicLinkService


def get_email_service(
    http_manager: AsyncHTTPManager = Depends(get_async_http_manager),
    template_renderer: TemplateRenderer = Depends(get_template_renderer),
    settings: APISettings = Depends(get_settings),
) -> EmailService:
    return EmailService(http_manager, template_renderer, settings)


def get_forecast_service(
    redis_manager: AsyncRedisManager = Depends(get_async_redis_manager),
    surf_spot_repo: AsyncSurfSpotRepository = Depends(get_surf_spot_repository),
) -> ForecastService:
    return ForecastService(redis_manager, surf_spot_repo)


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
    session: AsyncSession = Depends(get_async_db_session),
    settings: APISettings = Depends(get_settings),
) -> AuthService:
    return AuthService(
        redis_manager,
        security_manager,
        email_service,
        magic_link_service,
        user_repo,
        tier_repo,
        session,
        settings,
    )


def get_condition_profile_service(
    forecast_service: ForecastService = Depends(get_forecast_service),
    profile_repo: AsyncConditionProfileRepository = Depends(
        get_condition_profile_repository
    ),
    spot_repo: AsyncSurfSpotRepository = Depends(get_surf_spot_repository),
    session: AsyncSession = Depends(get_async_db_session),
) -> ConditionProfileService:
    return ConditionProfileService(forecast_service, profile_repo, spot_repo, session)


def get_crew_service(
    crew_repo: AsyncCrewRepository = Depends(get_crew_repository),
    user_repo: AsyncUserRepository = Depends(get_user_repository),
    spot_repo: AsyncSurfSpotRepository = Depends(get_surf_spot_repository),
    magic_link_service: MagicLinkService = Depends(get_magic_link_service),
    session: AsyncSession = Depends(get_async_db_session),
    settings: APISettings = Depends(get_settings),
) -> CrewService:
    return CrewService(
        crew_repo,
        user_repo,
        spot_repo,
        magic_link_service,
        session,
        settings,
    )
