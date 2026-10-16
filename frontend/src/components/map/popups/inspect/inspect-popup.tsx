import { useQuery } from "@tanstack/react-query";

import { MapPopup } from "@/components/ui/map";
import { getForecastPoint } from "@/api/forecasts";
import { pickValidTime } from "@/lib/forecast/point";
import { usePin, useInspectActions } from "@/stores/map-store";
import {
  useSelectedProvider,
  useSelectedModel,
  useModelFields,
} from "@/stores/selection-store";

import { TablePopup } from "./table-popup";

/*
 * InspectPopup = the mount seam. Reads the pin (view state, zustand), owns the
 * point query (server state, react-query), and portals a MapPopup positioned at
 * the pin. Mounts INSIDE <Map> so MapPopup's useMap() resolves. Pin null ->
 * returns null -> React unmounts -> MapPopup cleanup removes the maplibre popup.
 *
 * Popup content is paused at the table shell (see TablePopup). The glyph dial
 * and its mode toggle were removed; the glyph lib and `inspectMode` store state
 * are kept for when that work resumes.
 */

export function InspectPopup() {
  const pin = usePin();
  const provider = useSelectedProvider();
  const model = useSelectedModel();
  const fields = useModelFields();
  const { clearPin } = useInspectActions();

  const { data } = useQuery({
    queryKey: ["point", provider, model, pin?.lng, pin?.lat],
    queryFn: () =>
      getForecastPoint({
        provider: provider!,
        model: model!,
        lat: pin!.lat,
        lon: pin!.lng,
      }),
    enabled: !!pin && !!provider && !!model,
    staleTime: 1000 * 60 * 5,
  });

  if (!pin) return null;

  // TODO(now): hardcode "now" until the time-scrubber store exists; pickValidTime
  // will follow the scrubber timestamp once that lands.
  const point = data ? pickValidTime(data.points) : null;

  return (
    <MapPopup
      longitude={pin.lng}
      latitude={pin.lat}
      onClose={clearPin}
      closeButton
    >
      <TablePopup fields={fields} point={point} />
    </MapPopup>
  );
}
