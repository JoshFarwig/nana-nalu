import { Link, useRouterState } from "@tanstack/react-router";
import { MapPin, Map as MapIcon, Settings, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

type RouteLink = {
  to: string;
  icon: LucideIcon;
  label: string;
};

const ROUTE_LINKS: RouteLink[] = [
  { to: "/map", icon: MapIcon, label: "Map" },
  { to: "/spots", icon: MapPin, label: "Spots" },
  { to: "/settings", icon: Settings, label: "Settings" },
];

type SidebarProps = {
  children?: ReactNode;
  className?: string;
};

export function Sidebar({ children, className }: SidebarProps) {
  const { location } = useRouterState();

  return (
    <aside
      className={cn(
        "fixed top-2 left-2 bottom-2 z-30 flex w-12 flex-col items-center gap-1 rounded-lg border bg-background py-2 shadow-sm",
        className,
      )}
    >
      <nav className="flex flex-col gap-1">
        {ROUTE_LINKS.map(({ to, icon: Icon, label }) => {
          const active = location.pathname === to;
          return (
            <Button
              key={to}
              variant={active ? "secondary" : "ghost"}
              size="icon"
              asChild
              aria-label={label}
              title={label}
            >
              <Link to={to}>
                <Icon className="size-4" />
              </Link>
            </Button>
          );
        })}
      </nav>

      {children && (
        <>
          <div className="my-1 h-px w-6 bg-border" />
          <div className="flex flex-col gap-1">{children}</div>
        </>
      )}
    </aside>
  );
}

type SidebarToolProps = {
  icon: LucideIcon;
  label: string;
  active?: boolean;
  onClick: () => void;
};

export function SidebarTool({
  icon: Icon,
  label,
  active = false,
  onClick,
}: SidebarToolProps) {
  return (
    <Button
      variant={active ? "secondary" : "ghost"}
      size="icon"
      onClick={onClick}
      aria-label={label}
      title={label}
    >
      <Icon className="size-4" />
    </Button>
  );
}
