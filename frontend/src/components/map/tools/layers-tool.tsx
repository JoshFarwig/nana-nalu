import { SidebarTool } from "@/components/sidebar";
import {
  DataSelectionField,
  DataSelectionStatus,
  FieldSelect,
  ModelSelect,
  ProviderSelect,
} from "@/components/data-selection";
import { useState } from "react";
import { Layers2 } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";

export function LayersTool() {
  const [open, setOpen] = useState(false);

  return (
    <>
      <SidebarTool
        icon={Layers2}
        label="Map Layers"
        active={open}
        onClick={() => setOpen((o) => !o)}
      />

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="left" variant="floating">
          <SheetHeader>
            <SheetTitle className="flex items-center gap-2">
              <Layers2 className="size-4" />
              Layers Tool
            </SheetTitle>
            <SheetDescription>
              Pick a provider, model, and field to enable layer rendering.
            </SheetDescription>
          </SheetHeader>

          <div className="flex flex-col gap-4 px-6">
            <DataSelectionStatus>
              <DataSelectionField label="Provider">
                <ProviderSelect />
              </DataSelectionField>
              <DataSelectionField label="Model">
                <ModelSelect />
              </DataSelectionField>
              <DataSelectionField label="Field">
                <FieldSelect />
              </DataSelectionField>
            </DataSelectionStatus>
            {/* Future: layer visibility toggles, opacity sliders, basemap picker */}
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
