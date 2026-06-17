import {
  Field,
  FieldContent,
  FieldDescription,
  FieldLabel,
} from "@/components/ui/field";
import { Switch } from "@/components/ui/switch";
import type { LucideIcon } from "lucide-react";

type LayerToggleProps = {
  id: string;
  label: string;
  description?: string;
  Icon: LucideIcon;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
};

export function LayersToggle({
  id,
  label,
  description,
  Icon,
  checked,
  onCheckedChange,
}: LayerToggleProps) {
  return (
    <Field orientation="horizontal" className="max-w-sm">
      <FieldContent className="min-w-0">
        <FieldLabel htmlFor={id} className="items-center gap-2">
          <Icon className="size-4" />
          {label}
        </FieldLabel>
        {description && (
          <FieldDescription className="break-words">
            {description}
          </FieldDescription>
        )}
      </FieldContent>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onCheckedChange}
        className="self-center"
      />
    </Field>
  );
}
