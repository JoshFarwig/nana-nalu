import { useEffect, useRef } from "react";
import { MapboxOverlay } from "@deck.gl/mapbox";
import * as WeatherLayers from "weatherlayers-gl";

import { useMap } from "@/components/ui/map";
import { useLayerVisible } from "@/stores/map-store";

/*
 * SPIKE: FieldmapLayer = weatherlayers-gl RasterLayer over the MapLibre map.
 * Loads one hand-encoded 8-bit PNG (public/spike/swh.png, see scratchpad
 * encode_spike.py). Not wired to the selection store or backend yet. Goal is
 * only to prove: PNG -> loadTextureData -> imageUnscale -> palette -> smooth raster.
 * Deck runs non-interleaved (own canvas above the basemap) for the spike.
 */

type SpikeMeta = {
  vmin: number;
  vmax: number;
  bounds: [number, number, number, number]; // west, south, east, north
};

// stops are in real units (m); the layer unscales the 8-bit PNG back to this range
const WAVE_PALETTE: [number, [number, number, number]][] = [
  [0, [236, 248, 251]],
  [0.5, [158, 202, 225]],
  [1, [66, 146, 198]],
  [1.5, [253, 208, 162]],
  [2, [253, 141, 60]],
  [3, [215, 48, 31]],
  [4, [127, 0, 0]],
];

export function FieldmapLayer() {
  const { map, isLoaded } = useMap();
  const visible = useLayerVisible("fieldmap");
  const overlayRef = useRef<MapboxOverlay | null>(null);

  useEffect(() => {
    if (!map || !isLoaded) return;
    const overlay = new MapboxOverlay({ interleaved: false, layers: [] });
    map.addControl(overlay);
    overlayRef.current = overlay;
    return () => {
      map.removeControl(overlay);
      overlayRef.current = null;
    };
  }, [map, isLoaded]);

  useEffect(() => {
    const overlay = overlayRef.current;
    if (!overlay || !map || !isLoaded) return;
    if (!visible) {
      overlay.setProps({ layers: [] });
      return;
    }

    const ctrl = new AbortController();
    (async () => {
      const [image, meta] = await Promise.all([
        WeatherLayers.loadTextureData("/spike/swh.png"),
        fetch("/spike/swh.json").then((r) => r.json() as Promise<SpikeMeta>),
      ]);
      if (ctrl.signal.aborted) return;

      overlay.setProps({
        layers: [
          new WeatherLayers.RasterLayer({
            id: "fieldmap",
            image,
            imageType: "SCALAR",
            imageUnscale: [meta.vmin, meta.vmax],
            imageInterpolation: "LINEAR",
            imageMinValue: 0.01, // land is encoded as 0 -> hide it
            bounds: meta.bounds,
            palette: WAVE_PALETTE,
            opacity: 0.8,
          }),
        ],
      });
    })().catch((e) => console.error("[fieldmap] load failed", e));

    return () => ctrl.abort();
  }, [map, isLoaded, visible]);

  return null;
}
