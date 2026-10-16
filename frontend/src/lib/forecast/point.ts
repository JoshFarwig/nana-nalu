import type { FieldMeta, ForecastPoint } from "@/api/forecasts";

/**
 * Walk a dot-path (from FieldMeta.path, e.g. "wave.primary_swell.height")
 * into a ForecastPoint and return the numeric leaf, or null if any segment
 * is missing / the leaf isn't a number.
 */

export function valueAtPath(point: ForecastPoint, path: string): number | null {
  const leaf = path
    .split(".")
    .reduce<unknown>(
      (cursor, key) =>
        cursor && typeof cursor === "object"
          ? (cursor as Record<string, unknown>)[key]
          : undefined,
      point,
    );

  return typeof leaf === "number" ? leaf : null;
}

export function pickValidTime(
  points: ForecastPoint[],
  at?: string,
): ForecastPoint | null {
  if (points.length === 0) return null;
  const target = at ? Date.parse(at) : Date.now();
  return points.reduce((best, p) =>
    Math.abs(Date.parse(p.valid_time) - target) <
    Math.abs(Date.parse(best.valid_time) - target)
      ? p
      : best,
  );
}

export function formatValue(field: FieldMeta, value: number | null): string {
  if (value === null) return "—";
  if (field.viz_type === "directional")
    return `${Math.round(value)}${field.unit}`;
  return `${value.toFixed(1)} ${field.unit}`;
}
