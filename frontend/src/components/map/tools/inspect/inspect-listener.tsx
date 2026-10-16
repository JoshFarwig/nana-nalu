import { useEffect } from "react";

import { useMap } from "@/components/ui/map";
import { useInspectActive, useMapStore } from "@/stores/map-store";

export function InspectToolListener() {
  const { map } = useMap();
  const active = useInspectActive();

  useEffect(() => {
    if (!map || !active) return;
    const canvas = map.getCanvas();
    canvas.style.cursor = "crosshair";

    const onClick = (e: maplibregl.MapMouseEvent) => {
      useMapStore.getState().setPin({ lng: e.lngLat.lng, lat: e.lngLat.lat });
    };

    map.on("click", onClick);

    return () => {
      map.off("click", onClick);
      canvas.style.cursor = "";
    };
  }, [map, active]);

  return null;
}
