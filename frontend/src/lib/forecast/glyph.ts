import type { FieldMeta, ForecastPoint } from "@/api/forecasts";
import { valueAtPath } from "./point";

// Glyph = forecast-viz domain (knows FieldMeta/ForecastPoint), not generic geo.
// The dial renders ONE arrow per directional component the model produced,
// driven off FieldMeta `group`/`role`, so a wave model shows swell arrows and a
// wind model shows a wind arrow automatically (no hardcoded channel list).
// Scope: the dial shows directional components only. Scalar-only readings
// (period, tide level, a swell height with no direction) are NOT on the dial,
// they live in the inspect popup's time-series table. This keeps the dial bounded
// by physics (how many directional phenomena), not by catalog size.

export type DirectionConvention = "from" | "toward";

// One dial element: an arrow (required) with its paired magnitude (optional).
export type GlyphChannel = {
  group: string; // physical component, e.g. "combined_sea", "wind"
  label: string; // magnitude label if present, else the direction's label
  direction: {
    field: FieldMeta;
    degrees: number; // raw compass value as stored (degrees true)
    convention: DirectionConvention;
    rotationCss: number; // CSS rotate(deg) for the arrow — see directionToRotation
  };
  magnitude?: { field: FieldMeta; value: number }; // chip text + arrow length/color
};

/**
 * Group the model's fields by physical component and emit one GlyphChannel per
 * component that HAS a non-null direction at this timestep. Magnitude (role
 * "magnitude") attaches to the arrow when present. Period / tide / dir-less
 * components produce no channel — they belong to the popup table, not the dial.
 */

export function buildGlyphChannels(
  fields: FieldMeta[],
  point: ForecastPoint,
): GlyphChannel[] {
  // bucket fields by their declared group
  const groups = new Map<string, FieldMeta[]>();
  for (const f of fields) {
    const bucket = groups.get(f.group);
    if (bucket) bucket.push(f);
    else groups.set(f.group, [f]);
  }

  const channels: GlyphChannel[] = [];
  for (const [group, members] of groups) {
    const dirField = members.find((f) => f.role === "direction");
    if (!dirField) continue; // no direction -> not a dial element
    const degrees = valueAtPath(point, dirField.path);
    if (degrees == null) continue; // no value this timestep -> skip

    // backend guarantees this is set for role==="direction"; guard narrows the
    // optional (undefined) away and documents the invariant the validator enforces
    const convention = dirField.direction_convention;
    if (convention == null) continue;

    const magField = members.find((f) => f.role === "magnitude");
    const magValue = magField ? valueAtPath(point, magField.path) : null;
    const magnitude =
      magField && magValue != null
        ? { field: magField, value: magValue }
        : undefined;

    channels.push({
      group,
      label: magnitude?.field.label ?? dirField.label,
      direction: {
        field: dirField,
        degrees,
        convention,
        rotationCss: directionToRotation(degrees, convention),
      },
      magnitude,
    });
  }
  return channels;
}

export function directionToRotation(
  degrees: number,
  convention: DirectionConvention,
): number {
  switch (convention) {
    case "from":
      return (degrees + 180) % 360;
    case "toward":
      return degrees % 360;
    default:
      return 0;
  }
}
