from dataclasses import dataclass

from core.config import PrefectSettings, load_settings
from core.database import SyncDatabaseManager
from core.http import SyncHTTPManager


@dataclass
class ForecastResources:
    http: SyncHTTPManager
    db: SyncDatabaseManager
    settings: PrefectSettings

    def close(self) -> None:
        """Clean up all resources."""
        self.http.close()
        self.db.close()


_RESOURCES: ForecastResources | None = None


def get_resources() -> ForecastResources:
    """
    Lazy inits and return worker global resource singletons
    """
    global _RESOURCES
    if _RESOURCES is None:
        settings = load_settings("prefect")
        _RESOURCES = ForecastResources(
            http=SyncHTTPManager(settings.http),
            db=SyncDatabaseManager(settings.db),
            settings=settings,
        )
    return _RESOURCES
