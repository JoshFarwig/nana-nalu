import { createRootRoute, Outlet } from "@tanstack/react-router";
import { TanStackRouterDevtools } from "@tanstack/react-router-devtools";

import { CornerPill } from "@/components/corner-pill";
import { ThemeProvider } from "@/components/theme-provider";

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  return (
    <ThemeProvider defaultTheme="dark" storageKey="vite-ui-theme">
      <div className="relative h-screen w-full">
        <main className="h-full w-full overflow-hidden">
          <Outlet />
        </main>
        <CornerPill />
        <TanStackRouterDevtools />
      </div>
    </ThemeProvider>
  );
}
