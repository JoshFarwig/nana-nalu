from schemas.forecast_schema import FieldMeta
from services.forecast.nomads_config import NOMADS_CONFIG_REGISTRY
from services.forecast.pacioos_config import PACIOOS_CONFIG_REGISTRY

provider_config_registries = [NOMADS_CONFIG_REGISTRY, PACIOOS_CONFIG_REGISTRY]


def get_fields_for_run(provider: str, model: str, region: str) -> list[FieldMeta]:
    """Return FieldMeta list for a (provider, model, region) combo across all registries."""
    for registry in provider_config_registries:
        for config in registry.values():
            if (
                config.provider_name.value == provider
                and config.model_name.value == model
                and config.region.value == region
            ):
                return config.fields
    raise ValueError(f"No config found for {provider}/{model}/{region}")
