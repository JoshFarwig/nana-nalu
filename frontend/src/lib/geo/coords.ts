// Mirrors backend MAX_COORD_DP (schemas/forecast_schema.py). Backend already
// rounds coords per grid resolution before sending; this is the float-noise
// floor for client-side modulo conversions — idempotent on backend values.
export const MAX_COORD_DP = 6;

/** Round to `precision` decimal places (JS Math.round is int-only). */
function roundTo(value: number, precision: number): number {
  const factor = 10 ** precision;
  return Math.round(value * factor) / factor;
}

export function longitudeTo180(
  longitude: number,
  precision: number = MAX_COORD_DP,
): number {
  // mirror Python longitude_to_180: round(((longitude + 180) % 360) - 180, p)
  // extra ((x % 360) + 360) % 360 keeps JS % positive for negative inputs
  const wrapped = (((longitude + 180) % 360) + 360) % 360;
  return roundTo(wrapped - 180, precision);
}

export function longitudeTo360(
  longitude: number,
  precision: number = MAX_COORD_DP,
): number {
  // mirror Python longitude_to_360: round(longitude % 360, precision)
  // JS % keeps sign of dividend, so normalize negatives first
  return roundTo(((longitude % 360) + 360) % 360, precision);
}
