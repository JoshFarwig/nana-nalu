import { useState } from "react";

import { Crosshair } from "lucide-react";

import { SidebarTool } from "@/components/sidebar";

import { Sheet, SheetContent } from "@/components/ui/sheet";

export function InspectTool() {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <SidebarTool
        icon={Crosshair}
        label="Inspect Tool"
        active={open}
        onClick={() => setOpen((o) => !o)}
      />

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent
          side="left"
          variant="floating"
          className="overflow-x-hidden"
        ></SheetContent>
      </Sheet>
    </div>
  );
}
