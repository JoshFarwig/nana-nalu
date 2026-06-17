import { SidebarTool } from "@/components/sidebar";
import {
  DataSelectionField,
  DataSelectionStatus,
  FieldSelect,
  ModelSelect,
  ProviderSelect,
} from "@/components/data-selection";
import { useState } from "react";
import { Layers2, Waves, SlidersHorizontal, MapPin } from "lucide-react";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { LayersToggle } from "./layer-toggle";

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
        <SheetContent
          side="left"
          variant="floating"
          className="overflow-x-hidden"
        >
          <div className="flex flex-col min-w-0">
            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                <Waves className="size-4" />
                Data Selection
              </SheetTitle>
              <SheetDescription>
                Pick a provider, model, and field to narrow data for the inspect
                tool and your field map layer.
              </SheetDescription>
            </SheetHeader>

            {/* Data selection context / statuses */}
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
            </div>

            <SheetHeader>
              <SheetTitle className="flex items-center gap-2">
                <Layers2 className="size-4" />
                Map Layers
              </SheetTitle>
              <SheetDescription>
                Toggle any layers you'd like selected
              </SheetDescription>
            </SheetHeader>

            {/* Map Layer selection, some defaults set*/}
            <div className="flex flex-col gap-4 px-6">
              <LayersToggle
                id="fieldmap"
                label="Field map"
                description="Shows a smoothed map layer of your selected field value."
                Icon={SlidersHorizontal}
                checked={true}
                onCheckedChange={() => {
                  console.log("I checked!");
                }}
              />
              <LayersToggle
                id="spots"
                label="Saved Spots"
                description="Renders all your saved surf spots."
                Icon={MapPin}
                checked={false}
                onCheckedChange={() => {
                  console.log("I checked!");
                }}
              />
            </div>
          </div>
        </SheetContent>
      </Sheet>
    </>
  );
}
