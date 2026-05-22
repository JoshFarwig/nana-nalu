import { createFileRoute } from "@tanstack/react-router";
import { Layers } from "lucide-react";
import { useState } from "react";

import { Map } from "@/components/ui/map";
import {
  ProviderModelPanel,
  type ProviderModelSelection,
} from "@/components/provider-model-panel";
import { Sidebar, SidebarTool } from "@/components/sidebar";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

export const Route = createFileRoute("/map")({
  component: MapPage,
});

type ToolId = "data-source" | null;

function MapPage() {
  const [openTool, setOpenTool] = useState<ToolId>(null);
  const [selection, setSelection] = useState<ProviderModelSelection>({
    providerId: "nomads",
    modelId: "nwps",
    fieldId: null,
  });

  const handleToggleTool = (id: Exclude<ToolId, null>) => {
    setOpenTool((prev) => (prev === id ? null : id));
  };

  return (
    <>
      <Map center={[-156.5, 20.5]} zoom={6} />

      <Sidebar>
        <SidebarTool
          icon={Layers}
          label="Data source"
          active={openTool === "data-source"}
          onClick={() => handleToggleTool("data-source")}
        />
      </Sidebar>

      <Sheet
        open={openTool === "data-source"}
        onOpenChange={(open) => setOpenTool(open ? "data-source" : null)}
      >
        <SheetContent side="left" className="ml-14 w-80">
          <SheetHeader>
            <SheetTitle>Data Source</SheetTitle>
            <SheetDescription>
              Pick provider, model, and optionally a field to filter popups.
            </SheetDescription>
          </SheetHeader>
          <div className="px-4 pb-4">
            <ProviderModelPanel
              className="w-full"
              onSelectionChange={setSelection}
            />
          </div>
        </SheetContent>
      </Sheet>

      {/* TODO: wire `selection` into map popups + field filtering */}
      {selection.fieldId && null}
    </>
  );
}
