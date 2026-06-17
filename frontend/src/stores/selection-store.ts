import { create } from "zustand";
import { useShallow } from "zustand/shallow";

import {
  type DataSelection,
  EMPTY_SELECTION,
  findCombo,
  firstCombo,
  resolveProvider,
  resolveModel,
  resolveField,
  availableProviders,
  availableModels,
  availableFields,
  selectedField,
} from "@/lib/data-selection";
import { type AvailableRunsResponse } from "@/api/forecasts";

type Status = "loading" | "ready" | "empty" | "error";

type SelectionState = {
  available: AvailableRunsResponse | null;
  selection: DataSelection;
  status: Status;
  userTouched: boolean;
  setAvailable: (data: AvailableRunsResponse | null, status: Status) => void;
  setProvider: (id: string) => void;
  setModel: (id: string) => void;
  setField: (id: string) => void;
};

export const useSelectionStore = create<SelectionState>((set, get) => ({
  available: null,
  selection: EMPTY_SELECTION,
  status: "loading",
  userTouched: false,

  setAvailable: (data, status) =>
    set((s) => {
      if (!data) return { available: data, status };

      // NOTE: safeguard to check combo still exists in data
      // in-case user selection deprecates during usage
      // i.e model run from X provider no longer generating,
      // PacIOOS models during government shutdown not generating data.
      const sel = s.selection;
      const keep =
        s.userTouched &&
        sel.provider != null &&
        sel.model != null &&
        sel.field != null &&
        !!findCombo(data, sel.provider, sel.model, sel.field);

      if (keep) return { available: data, status };

      const seeded =
        findCombo(data, "nomads", "nwps", "wave_significant_height") ??
        firstCombo(data) ??
        EMPTY_SELECTION;
      return { available: data, selection: seeded, status };
    }),

  setProvider: (id: string) => {
    const { available, selection } = get();
    if (!available) return;
    set({
      selection: resolveProvider(available, id, selection.field),
      userTouched: true,
    });
  },

  setModel: (id: string) => {
    const { available, selection } = get();
    if (!available || selection.provider == null) return;
    set({
      selection: resolveModel(
        available,
        selection.provider,
        id,
        selection.field,
      ),
      userTouched: true,
    });
  },

  setField: (id: string) => {
    const { available, selection } = get();
    if (!available) return;
    set({
      selection: resolveField(selection, id),
      userTouched: true,
    });
  },
}));

// slice hooks

export const useSelectionStatus = () => useSelectionStore((s) => s.status);

export const useSelectedProvider = () =>
  useSelectionStore((s) => s.selection.provider);

export const useSelectedModel = () =>
  useSelectionStore((s) => s.selection.model);

// raw selected field id — optional focus, binds the <Select value>
export const useSelectedField = () =>
  useSelectionStore((s) => s.selection.field);

// resolved FieldMeta for the selected field — used by inspect / top bar
// (returns a stable ref into `available`, so no useShallow needed)
export const useSelectedFieldMetadata = () =>
  useSelectionStore((s) => selectedField(s.available, s.selection));

export const useProviderOptions = () =>
  useSelectionStore(
    useShallow((s) => (s.available ? availableProviders(s.available) : [])),
  );

export const useModelOptions = () =>
  useSelectionStore(
    useShallow((s) =>
      s.available ? availableModels(s.available, s.selection.provider) : [],
    ),
  );

export const useFieldOptions = () =>
  useSelectionStore(
    useShallow((s) =>
      s.available
        ? availableFields(s.available, s.selection.provider, s.selection.model)
        : [],
    ),
  );

export const useSelectionActions = () =>
  useSelectionStore(
    useShallow((s) => ({
      setProvider: s.setProvider,
      setModel: s.setModel,
      setField: s.setField,
    })),
  );
