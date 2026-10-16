import { create, type StateCreator } from "zustand";
import { useShallow } from "zustand/shallow";

// map-store = how the map *presents* data (view domain).
// selection-store = *what* data (provider/model/field). Keep separate.
// Sliced so re-renders stay narrow and the file stays readable as it grows.

type Pin = { lng: number; lat: number };

// which face of the inspect popup is showing: the directional dial or the table
export type InspectMode = "glyph" | "table";

// inspect slice

type InspectSlice = {
  inspectActive: boolean;
  pin: Pin | null;
  showCell: boolean; // sticky pref: render the grid-cell footprint (provenance)
  inspectMode: InspectMode; // sticky pref: popup face (dial vs time-series table)

  setInspectActive: (v: boolean) => void;
  toggleInspect: () => void;
  setPin: (p: Pin) => void;
  clearPin: () => void;
  toggleCell: () => void;
  setInspectMode: (m: InspectMode) => void;
  toggleInspectMode: () => void;
};

const createInspectSlice: StateCreator<MapStore, [], [], InspectSlice> = (
  set,
) => ({
  inspectActive: false,
  pin: null,
  showCell: false,
  inspectMode: "glyph",

  setInspectActive: (v) =>
    set({ inspectActive: v, ...(v ? {} : { pin: null }) }),

  toggleInspect: () =>
    set((s) => ({
      inspectActive: !s.inspectActive,
      pin: s.inspectActive ? null : s.pin,
    })),

  setPin: (p) => set({ pin: p }),
  clearPin: () => set({ pin: null }),
  toggleCell: () => set((s) => ({ showCell: !s.showCell })),
  setInspectMode: (m) => set({ inspectMode: m }),
  toggleInspectMode: () =>
    set((s) => ({ inspectMode: s.inspectMode === "glyph" ? "table" : "glyph" })),
});

// layers slice: which map layers are toggled on

type LayersSlice = {
  layerVisibility: Record<string, boolean>;
  setLayer: (id: string, visible: boolean) => void;
  toggleLayer: (id: string) => void;
};

const createLayersSlice: StateCreator<MapStore, [], [], LayersSlice> = (
  set,
) => ({
  layerVisibility: { fieldmap: true, spots: false },

  setLayer: (id, visible) =>
    set((s) => ({ layerVisibility: { ...s.layerVisibility, [id]: visible } })),

  toggleLayer: (id) =>
    set((s) => ({
      layerVisibility: { ...s.layerVisibility, [id]: !s.layerVisibility[id] },
    })),
});

type MapStore = InspectSlice & LayersSlice;

export const useMapStore = create<MapStore>()((...a) => ({
  ...createInspectSlice(...a),
  ...createLayersSlice(...a),
}));

// slice hooks

export const useInspectActive = () => useMapStore((s) => s.inspectActive);
export const usePin = () => useMapStore((s) => s.pin);
export const useShowCell = () => useMapStore((s) => s.showCell);
export const useInspectMode = () => useMapStore((s) => s.inspectMode);

export const useLayerVisible = (id: string) =>
  useMapStore((s) => s.layerVisibility[id] ?? false);

export const useLayerActions = () =>
  useMapStore(
    useShallow((s) => ({ setLayer: s.setLayer, toggleLayer: s.toggleLayer })),
  );

export const useInspectActions = () =>
  useMapStore(
    useShallow((s) => ({
      toggleInspect: s.toggleInspect,
      clearPin: s.clearPin,
      setInspectMode: s.setInspectMode,
      toggleInspectMode: s.toggleInspectMode,
    })),
  );
