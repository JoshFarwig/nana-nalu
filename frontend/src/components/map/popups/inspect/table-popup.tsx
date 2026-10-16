import type { FieldMeta, ForecastPoint } from "@/api/forecasts";
import { cn } from "@/lib/utils";

/*
 * TablePopup = the inspect popup body. PAUSED: renders the table shell only
 * (field labels, no values). The point query and selection plumbing stay wired
 * in InspectPopup so values and the scrubber time series can land here later.
 */

type TablePopupProps = {
  fields: FieldMeta[];
  point: ForecastPoint | null;
  className?: string;
};

export function TablePopup({ fields, className }: TablePopupProps) {
  if (fields.length === 0) {
    return (
      <p className="text-muted-foreground text-xs">No fields available.</p>
    );
  }

  return (
    <table className={cn("w-full text-xs", className)}>
      <tbody>
        {fields.map((f) => (
          <tr key={f.id} className="border-border/50 border-b last:border-0">
            <td className="text-muted-foreground py-1 pr-3">{f.label}</td>
            <td className="py-1 text-right tabular-nums">—</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
