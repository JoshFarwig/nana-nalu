# NOTE: for a long time, I really struggled against being extra verbose with
# Async and Sync Managers and Repos. my initial thought process was
# to try and keep most code DRY, and hence stick to working in async contexts.
# however, after trying to force async code in celery, it seems like async
# functionality for this project in the celery worker context was really not
# needed for its purpose. The only real benefit would be if multiple network
# requests were required for a provider (i.e. surfline v2 api), but in this
# niche case, the api likely requires some kind of rate limiting anyways and
# defeats this purpose. Openmeteo has request batching built in as well, so
# async setups such that a single fetch for a provider is a seperate task,
# really didn't make much sense for the overhead and complexity.

from .user_repository import AsyncUserRepository, SyncUserRepository
from .surf_spot_repository import AsyncSurfSpotRepository, SyncSurfSpotRepository


__all__ = [
    "AsyncUserRepository",
    "SyncUserRepository",
    "AsyncSurfSpotRepository",
    "SyncSurfSpotRepository",
]
