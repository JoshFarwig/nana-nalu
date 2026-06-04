import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useQuery } from "@tanstack/react-query";

import { getAvailable } from "@/api/forecasts";
import {
  EMPTY_SELECTION,
  availableFields,
  availableModels,
  availableProviders,
  findCombo,
  firstCombo,
  resolveField,
  resolveModel,
  resolveProvider,
  type DataSelection,
} from "@/lib/data-selection";

type Status = "loading" | "ready" | "empty" | "error";

type DataSelectionContextState = {
  selection: DataSelection;
  status: Status;
  options: {
    providers: ReturnType<typeof availableProviders>;
    models: ReturnType<typeof availableModels>;
    fields: ReturnType<typeof availableFields>;
  };
  setProvider: (id: string) => void;
  setModel: (id: string) => void;
  setField: (id: string) => void;
};

const DataSelectionContext = createContext<DataSelectionContextState | null>(
  null,
);

export function DataSelectionProvider({ children }: { children: ReactNode }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["available"],
    queryFn: getAvailable,
    staleTime: 1000 * 60 * 60,
  });

  const [override, setOverride] = useState<DataSelection | null>(null);

  const selection: DataSelection = useMemo(() => {
    if (override) return override;
    if (!data) return EMPTY_SELECTION;
    return (
      findCombo(data, "nomads", "nwps", "wave_significant_height") ??
      firstCombo(data) ??
      EMPTY_SELECTION
    );
  }, [data, override]);

  const options = useMemo(
    () => ({
      providers: data ? availableProviders(data) : [],
      models: data ? availableModels(data, selection.provider) : [],
      fields: data
        ? availableFields(data, selection.provider, selection.model)
        : [],
    }),
    [data, selection.provider, selection.model],
  );

  const setProvider = (id: string) => {
    if (!data) return;
    setOverride(resolveProvider(data, id, selection.field));
  };

  const setModel = (id: string) => {
    if (!data || !selection.provider) return;
    setOverride(resolveModel(data, selection.provider, id, selection.field));
  };

  const setField = (id: string) => {
    setOverride(resolveField(selection, id));
  };

  const status: Status = isError
    ? "error"
    : isLoading
      ? "loading"
      : !data || data.providers.length === 0
        ? "empty"
        : "ready";

  return (
    <DataSelectionContext.Provider
      value={{ selection, status, options, setProvider, setModel, setField }}
    >
      {children}
    </DataSelectionContext.Provider>
  );
}

export function useDataSelection() {
  const ctx = useContext(DataSelectionContext);
  if (!ctx)
    throw new Error("useDataSelection must be inside DataSelectionProvider");
  return ctx;
}
