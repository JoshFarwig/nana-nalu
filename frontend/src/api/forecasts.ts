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

export type SwellPartition = {
  height: number | null;
  period: number | null;
  direction: number | null;
};

export type WaveData = {
  significant_height: number | null;
  peak_period: number | null;
  peak_direction: number | null;
  wind_wave_height: number | null;
  wind_wave_period: number | null;
  wind_wave_direction: number | null;
  primary_swell: SwellPartition | null;
  secondary_swell: SwellPartition | null;
  tertiary_swell: SwellPartition | null;
};

export type WindData = { speed: number | null; direction: number | null };
export type CurrentData = { speed: number | null; direction: number | null };
export type TideData = { height: number | null };

export type ForecastPoint = {
  valid_time: string; // ISO
  wave: WaveData | null;
  wind: WindData | null;
  tide: TideData | null;
  current: CurrentData | null;
};

export type PointForecastResponse = {
  provider: string;
  model: string;
  region: string;
  run_time: string;
  lat: number;
  lon: number;
  points: ForecastPoint[];
};

export async function getForecastPoint(p: {
  provider: string;
  model: string;
  lat: number;
  lon: number;
  validTime?: string;
}): Promise<PointForecastResponse> {
  return apiFetch("/forecasts/point", {
    provider: p.provider,
    model: p.model,
    lat: String(p.lat),
    lon: String(p.lon), // raw lng, backend normalizes
    ...(p.validTime ? { valid_time: p.validTime } : {}),
  });
}
// getForecastGrind()

// API functions

export async function getAvailable(): Promise<AvailableRunsResponse> {
  return await apiFetch("/forecasts/available");
}
