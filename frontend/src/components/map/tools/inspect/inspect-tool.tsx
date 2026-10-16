import { Crosshair } from "lucide-react";

import { SidebarTool } from "@/components/sidebar";
import { useInspectActive, useInspectActions } from "@/stores/map-store";

/*
 * InspectTool = the arming switch, not a panel. Toggling it flips `inspectActive`
 * in the store; that arms InspectToolListener (crosshair cursor + click-to-pin).
 * The readout itself is the map popup, so there's no sheet here.
 */

export function InspectTool() {
  const active = useInspectActive();
  const { toggleInspect } = useInspectActions();

  return (
    <SidebarTool
      icon={Crosshair}
      label="Inspect Tool"
      active={active}
      onClick={toggleInspect}
    />
  );
}
