from utils.location import Location
from configs import NWPSModelConfig, NWPSMauiModel

NWPS_MODELS: dict[Location, NWPSModelConfig] = {
    Location.MAUI: NWPSMauiModel(),
}
