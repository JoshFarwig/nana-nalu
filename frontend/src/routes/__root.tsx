import { createRootRoute, Outlet } from "@tanstack/react-router";
import { TanStackRouterDevtools } from "@tanstack/react-router-devtools";
import { ReactQueryDevtools } from "@tanstack/react-query-devtools";

import { CornerPill } from "@/components/corner-pill";
import { AppProviders } from "@/contexts/app-providers";

export const Route = createRootRoute({
  component: RootLayout,
});

function RootLayout() {
  return (
    <AppProviders>
      <div className="relative h-screen w-full">
        <main className="h-full w-full overflow-hidden">
          <Outlet />
        </main>
        <CornerPill />
        {import.meta.env.DEV && (
          <>
            <ReactQueryDevtools />
            <TanStackRouterDevtools />
          </>
        )}
      </div>
    </AppProviders>
  );
}
