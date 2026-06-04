import { apiFetch } from "@/api/client";

// types mirrored from backend schemas/forecast_schema.py

// getAvailable()

export type FieldMeta = {
  id: string;
  path: string;
  label: string;
  unit: string;
  viz_type: "scalar" | "directional";
};

export type GridBounds = {
  lat_min: number;
  lat_max: number;
  lon_min: number;
  lon_max: number;
};

export type TimeHorizon = {
  start: string;
  end: string;
};

export type RegionInfo = {
  id: string;
  latest_run_time: string;
  bounds: GridBounds;
  horizon: TimeHorizon;
};

export type ModelInfo = {
  id: string;
  fields: FieldMeta[];
  regions: RegionInfo[];
};

export type ProviderInfo = {
  id: string;
  models: ModelInfo[];
};

export type AvailableRunsResponse = {
  providers: ProviderInfo[];
};

// getForecastPoint()

// getForecastGrind()

// API functions

export async function getAvailable(): Promise<AvailableRunsResponse> {
  return await apiFetch("/forecasts/available");
}
