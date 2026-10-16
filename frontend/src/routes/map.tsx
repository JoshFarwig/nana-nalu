import { createFileRoute } from "@tanstack/react-router";
import { Map } from "@/components/ui/map";
import { LayersTool } from "@/components/map/tools/layers/layers-tool";
import { Sidebar } from "@/components/sidebar";

import { useTheme } from "@/contexts/theme-context";
import { DataSelectionTool } from "@/components/map/tools/data-selection-tool";
import { InspectTool } from "@/components/map/tools/inspect/inspect-tool";
import { TimeScrubberTool } from "@/components/map/tools/time-scrubber-tool";
import { InspectToolListener } from "@/components/map/tools/inspect/inspect-listener";
import { FieldmapLayer } from "@/components/map/layers/fieldmap-layer";
import { InspectPopup } from "@/components/map/popups/inspect/inspect-popup";

export const Route = createFileRoute("/map")({
  component: MapPage,
});

function MapPage() {
  const { resolvedTheme } = useTheme();

  return (
    <>
      <Map theme={resolvedTheme} center={[-156.5, 20.5]} zoom={6}>
        {/* SPIKE: static sample PNG, dev only until the raster pipeline lands */}
        {import.meta.env.DEV && <FieldmapLayer />}
        <InspectToolListener />
        <InspectPopup />
      </Map>

      <Sidebar>
        <DataSelectionTool />
        <InspectTool />
        <LayersTool />
        <TimeScrubberTool />
      </Sidebar>
    </>
  );
}
