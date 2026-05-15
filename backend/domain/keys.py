"""
Value objects identifying a forecast model run.

ModelRunKey = (provider, model, region) triple. Provider-scoped model
enums prevent illegal pairs like (nomads, swan) at construction time.
Region enablement is env-driven, so registry membership stays runtime.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

from core.exceptions.forecasts import UnknownRunComboError
from domain.models import NOMADSModel, PacIOOSModel
from services.forecast.config_registries import provider_config_registries
from domain.region import Region


class _NomadsKey(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: Literal["nomads"]
    model: NOMADSModel
    region: Region


class _PacIOOSKey(BaseModel):
    model_config = ConfigDict(frozen=True)
    provider: Literal["pacioos"]
    model: PacIOOSModel
    region: Region


ModelRunKey = Annotated[
    _NomadsKey | _PacIOOSKey,
    Field(discriminator="provider"),
]

# Flat O(1) registry built once at import. Key = (provider, model, region) as strings.
_RUN_REGISTRY: dict[tuple[str, str, str], object] = {
    (cfg.provider_name, model_enum.value, region.value): cfg
    for registry in provider_config_registries
    for (region, model_enum), cfg in registry.items()
}


def validate_run_combo(key: ModelRunKey) -> ModelRunKey:
    """
    Confirm the triple exists in the active config registry.

    Type system guarantees (provider, model) is a legal pair.
    This check covers (provider, model, region) membership —
    a region may be enabled globally but not configured for this model.
    """
    lookup = (key.provider, key.model.value, key.region.value)
    if lookup in _RUN_REGISTRY:
        return key

    available = [
        {"model": m, "region": r} for (p, m, r) in _RUN_REGISTRY if p == key.provider
    ]
    raise UnknownRunComboError(
        key.provider, key.model.value, key.region.value, available
    )
