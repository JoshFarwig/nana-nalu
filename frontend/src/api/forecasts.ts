import { z } from "zod";
import { apiFetch } from "@/api/client";

// types mirrored from backend schemas/forecast_schema.py

// getAvailable()

const CoordBoundsSchema = z.object({
  lat_min: z.number(),
  lat_max: z.number(),
  lon_min: z.number(),
  lon_max: z.number(),
});

const TimeHorizonSchema = z.object({
  start: z.string(),
  end: z.string(),
});

const RegionInfoSchema = z.object({
  id: z.string(),
  latest_run_time: z.string(),
  region_bounds: CoordBoundsSchema,
  horizon: TimeHorizonSchema,
});

const FieldMetaSchema = z.object({
  id: z.string(),
  path: z.string(),
  label: z.string(),
  unit: z.string(),
  viz_type: z.enum(["scalar", "directional"]),
  group: z.string(),
  role: z.enum(["magnitude", "direction", "scalar"]),
  // absent for non-direction fields (backend strips None via exclude_none)
  direction_convention: z.enum(["from", "toward"]).optional(),
});

const ModelInfoSchema = z.object({
  id: z.string(),
  fields: z.array(FieldMetaSchema),
  regions: z.array(RegionInfoSchema),
});

const ProviderInfoSchema = z.object({
  id: z.string(),
  models: z.array(ModelInfoSchema),
});

const AvailableRunsResponseSchema = z.object({
  providers: z.array(ProviderInfoSchema),
});

export type FieldMeta = z.infer<typeof FieldMetaSchema>;
export type RegionInfo = z.infer<typeof RegionInfoSchema>;
export type ModelInfo = z.infer<typeof ModelInfoSchema>;
export type ProviderInfo = z.infer<typeof ProviderInfoSchema>;
export type AvailableRunsResponse = z.infer<typeof AvailableRunsResponseSchema>;

export async function getAvailable(): Promise<AvailableRunsResponse> {
  return await apiFetch("/forecasts/available", {
    schema: AvailableRunsResponseSchema,
  });
}

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

export type CellBounds = {
  lat_min: number;
  lat_max: number;
  lon_min: number;
  lon_max: number;
};

export type PointForecastResponse = {
  provider: string;
  model: string;
  region: string;
  cell_bounds: CellBounds;
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
  start?: string;
  end?: string;
}): Promise<PointForecastResponse> {
  return apiFetch("/forecasts/point", {
    params: {
      provider: p.provider,
      model: p.model,
      lat: String(p.lat),
      lon: String(p.lon), // raw lng, backend normalizes
      ...(p.validTime ? { valid_time: p.validTime } : {}),
      ...(p.start ? { start: p.start } : {}),
      ...(p.end ? { end: p.end } : {}),
    },
  });
}
