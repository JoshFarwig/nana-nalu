import { Moon, Sun, Monitor } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useTheme } from "@/contexts/theme-context";

const NEXT_THEME = {
  light: "dark",
  dark: "system",
  system: "light",
} as const;

const LABEL = {
  light: "Switch to dark",
  dark: "Switch to system",
  system: "Switch to light",
} as const;

export function ModeToggle() {
  const { theme, setTheme } = useTheme();
  const Icon = theme === "light" ? Sun : theme === "dark" ? Moon : Monitor;

  return (
    <Button
      variant="outline"
      size="icon"
      onClick={() => setTheme(NEXT_THEME[theme])}
      aria-label={LABEL[theme]}
      title={LABEL[theme]}
    >
      <Icon className="size-[1.2rem]" />
    </Button>
  );
}
