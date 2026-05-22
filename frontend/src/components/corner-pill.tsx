import { Link } from "@tanstack/react-router";

import { ModeToggle } from "@/components/mode-toggle";
import { useTheme } from "@/components/theme-provider";
import { cn } from "@/lib/utils";

type CornerPillProps = {
  className?: string;
};

export function CornerPill({ className }: CornerPillProps) {
  const { resolvedTheme } = useTheme();

  return (
    <div
      className={cn(
        "fixed top-2 right-2 z-30 flex items-center gap-2 rounded-lg border bg-background px-2 py-1 shadow-sm",
        className,
      )}
    >
      <Link to="/map" className="flex items-center">
        <img
          src={resolvedTheme === "dark" ? "/dark_logo.svg" : "/light_logo.svg"}
          className="h-7 w-auto"
          alt="Nana Nalu"
        />
      </Link>
      <ModeToggle />
    </div>
  );
}
