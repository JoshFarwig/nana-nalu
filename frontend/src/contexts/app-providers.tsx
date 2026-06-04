import { type ReactNode } from "react";
import {
  MutationCache,
  QueryCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { toast } from "sonner";

import { ThemeProvider } from "@/contexts/theme-context";
import { DataSelectionProvider } from "@/contexts/data-selection-context";
import { Toaster } from "@/components/ui/sonner";
import { ApiError } from "@/api/client";

const FALLBACK_MESSAGE = "Something went wrong. Please try again.";

function handleApiError(err: unknown, scope: "query" | "mutation") {
  const isApi = err instanceof ApiError;
  const userMessage =
    err instanceof Error ? err.message : FALLBACK_MESSAGE;

  if (import.meta.env.DEV) {
    console.error(`[${scope}]`, {
      message: userMessage,
      ...(isApi && {
        error_code: err.error_code,
        status: err.status,
        details: err.details,
      }),
      error: err,
    });
  }

  const description =
    import.meta.env.DEV && isApi
      ? `${err.error_code}${err.status ? ` · HTTP ${err.status}` : ""}`
      : undefined;

  toast.error(userMessage, { description });
}

const queryClient = new QueryClient({
  queryCache: new QueryCache({
    onError: (err) => handleApiError(err, "query"),
  }),
  mutationCache: new MutationCache({
    onError: (err) => handleApiError(err, "mutation"),
  }),
});

export function AppProviders({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider>
      <QueryClientProvider client={queryClient}>
        <DataSelectionProvider>{children}</DataSelectionProvider>
        <Toaster richColors closeButton />
      </QueryClientProvider>
    </ThemeProvider>
  );
}
