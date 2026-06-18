import { useState } from "react";

import { Clock } from "lucide-react";

import { SidebarTool } from "@/components/sidebar";
export function TimeScrubberTool() {
  const [open, setOpen] = useState(false);

  return (
    <div>
      <SidebarTool
        icon={Clock}
        label="Time Scrubber Tool"
        active={open}
        onClick={() => setOpen((o) => !o)}
      />
    </div>
  );
}
