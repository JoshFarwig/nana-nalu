from enum import Enum


class ForecastProvider(str, Enum):
    NOMADS = "nomads"
    PACIOOS = "pacioos"
