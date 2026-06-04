import type { ReactNode } from "react";

import { useDataSelection } from "@/contexts/data-selection-context";
import { Skeleton } from "./ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";

import { cn } from "@/lib/utils";

type FieldInfo = { id: string; label: string; unit: string | null };

function formatFieldLabel(field: FieldInfo): string {
  // TODO: decide how to render field label, store user pref in localStorage
  return field.label;
}

export function DataSelectionField({
  label,
  htmlFor,
  children,
}: {
  label: string;
  htmlFor?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-xs font-medium">
        {label}
      </label>
      {children}
    </div>
  );
}

export function DataSelectionStatus({ children }: { children: ReactNode }) {
  const { status } = useDataSelection();

  if (status === "empty") {
    return (
      <p className="text-destructive text-xs">
        No forecast providers available. Check backend ingest.
      </p>
    );
  }

  return <>{children}</>;
}

function ErrorStub({
  className,
  placeholder,
}: {
  className?: string;
  placeholder: string;
}) {
  return (
    <Select disabled>
      <SelectTrigger className={cn("w-full", className)} aria-invalid>
        <SelectValue placeholder={placeholder} />
      </SelectTrigger>
    </Select>
  );
}

export function ProviderSelect({ className }: { className?: string }) {
  const { selection, status, options, setProvider } = useDataSelection();

  if (status === "loading") return <Skeleton className="h-9 w-full" />;
  if (status === "error")
    return <ErrorStub className={className} placeholder="Unavailable" />;

  const isEmpty = options.providers.length === 0;

  return (
    <Select
      value={selection.provider ?? ""}
      onValueChange={setProvider}
      disabled={isEmpty}
    >
      <SelectTrigger className={cn("w-full", className)} aria-invalid={isEmpty}>
        <SelectValue placeholder="Select provider" />
      </SelectTrigger>
      <SelectContent>
        {options.providers.map((p) => (
          <SelectItem key={p.id} value={p.id}>
            {p.id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function ModelSelect({ className }: { className?: string }) {
  const { selection, status, options, setModel } = useDataSelection();

  if (status === "loading") return <Skeleton className="h-9 w-full" />;
  if (status === "error")
    return <ErrorStub className={className} placeholder="Unavailable" />;

  const isEmpty = options.models.length === 0;

  return (
    <Select
      value={selection.model ?? ""}
      onValueChange={setModel}
      disabled={isEmpty || !selection.provider}
    >
      <SelectTrigger className={cn("w-full", className)} aria-invalid={isEmpty}>
        <SelectValue placeholder="Select model" />
      </SelectTrigger>
      <SelectContent>
        {options.models.map((m) => (
          <SelectItem key={m.id} value={m.id}>
            {m.id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function FieldSelect({ className }: { className?: string }) {
  const { selection, status, options, setField } = useDataSelection();

  if (status === "loading") return <Skeleton className="h-9 w-full" />;
  if (status === "error")
    return <ErrorStub className={className} placeholder="Unavailable" />;

  const isEmpty = options.fields.length === 0;

  return (
    <Select
      value={selection.field ?? ""}
      onValueChange={setField}
      disabled={isEmpty || !selection.model}
    >
      <SelectTrigger className={cn("w-full", className)} aria-invalid={isEmpty}>
        <SelectValue placeholder="Select field" />
      </SelectTrigger>
      <SelectContent>
        {options.fields.map((f) => (
          <SelectItem key={f.id} value={f.id}>
            {formatFieldLabel(f)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
