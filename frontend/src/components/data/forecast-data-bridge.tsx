import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";

import { useSelectionStore } from "@/stores/selection-store";
import { getAvailable } from "@/api/forecasts";

/*
 * Headless react-query, zustand sync. Owns the ["available"] query and
 * mirrors its state into the selection store. Renders nothing.
 * TODO: Consider making an AppBridge component to wrap all headless components
 */

export const ForecastDataBridge = () => {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["available"],
    queryFn: getAvailable,
    staleTime: 1000 * 60 * 60,
  });

  const setAvailable = useSelectionStore((s) => s.setAvailable);

  useEffect(() => {
    const status = isError
      ? "error"
      : isLoading
        ? "loading"
        : !data || data.providers.length === 0
          ? "empty"
          : "ready";

    setAvailable(data ?? null, status);
  }, [data, isLoading, isError, setAvailable]);

  return null;
};
