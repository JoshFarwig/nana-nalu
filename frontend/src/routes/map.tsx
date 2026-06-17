import { createFileRoute } from "@tanstack/react-router";
import { Layers2, Locate, Clock } from "lucide-react";
import { useState } from "react";

import { Map } from "@/components/ui/map";
import { LayersTool } from "@/components/map/tools/layers-tool";
import { Sidebar, SidebarTool } from "@/components/sidebar";

import { useTheme } from "@/contexts/theme-context";

export const Route = createFileRoute("/map")({
  component: MapPage,
});

type ToolId = "layers" | "inspect" | "time" | null;

function MapPage() {
  const { resolvedTheme } = useTheme();
  const [openTool, setOpenTool] = useState<ToolId>(null);

  const handleToggleTool = (id: Exclude<ToolId, null>) => {
    setOpenTool((prev) => (prev === id ? null : id));
  };

  return (
    <>
      <Map theme={resolvedTheme} center={[-156.5, 20.5]} zoom={6} />

      <Sidebar>
        <LayersTool />
      </Sidebar>
    </>
  );
}
