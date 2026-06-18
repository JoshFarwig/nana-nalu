import { useState } from "react";

import { SlidersHorizontal } from "lucide-react";

import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";

import { SidebarTool } from "@/components/sidebar";
import {
  DataSelectionStatus,
  DataSelectionField,
  ProviderSelect,
  ModelSelect,
  FieldSelect,
} from "@/components/data-selection";

export function DataSelectionTool() {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <SidebarTool
        icon={SlidersHorizontal}
        label="Data Selection Tool"
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
                <SlidersHorizontal className="size-4" />
                Data Selection
              </SheetTitle>
              <SheetDescription>
                Pick a provider, model, and field to narrow data for the inspect
                tool and your map layer(s).
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
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
