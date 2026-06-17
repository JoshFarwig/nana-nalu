import type { ReactNode } from "react";

import {
  useSelectionStatus,
  useSelectionActions,
  useSelectedProvider,
  useSelectedModel,
  useSelectedField,
  useProviderOptions,
  useModelOptions,
  useFieldOptions,
} from "@/stores/selection-store";

import { Skeleton } from "./ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./ui/select";

import { type FieldMeta } from "@/api/forecasts";

import { cn } from "@/lib/utils";

function formatFieldLabel(field: FieldMeta): string {
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
  const status = useSelectionStatus();

  if (status === "empty") {
    return (
      <p className="text-destructive text-xs">
        No forecast providers available.
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
  const status = useSelectionStatus();
  const selectedProvider = useSelectedProvider();
  const providerOptions = useProviderOptions();
  const { setProvider } = useSelectionActions();

  if (status === "loading") return <Skeleton className="h-9 w-full" />;
  if (status === "error")
    return <ErrorStub className={className} placeholder="Unavailable" />;

  const isEmpty = providerOptions.length === 0;

  return (
    <Select
      value={selectedProvider ?? ""}
      onValueChange={setProvider}
      disabled={isEmpty}
    >
      <SelectTrigger className={cn("w-full", className)} aria-invalid={isEmpty}>
        <SelectValue placeholder="Select provider" />
      </SelectTrigger>
      <SelectContent>
        {providerOptions.map((p) => (
          <SelectItem key={p.id} value={p.id}>
            {p.id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function ModelSelect({ className }: { className?: string }) {
  const status = useSelectionStatus();
  const selectedProvider = useSelectedProvider();
  const selectedModel = useSelectedModel();
  const modelOptions = useModelOptions();
  const { setModel } = useSelectionActions();

  if (status === "loading") return <Skeleton className="h-9 w-full" />;
  if (status === "error")
    return <ErrorStub className={className} placeholder="Unavailable" />;

  const isEmpty = modelOptions.length === 0;

  return (
    <Select
      value={selectedModel ?? ""}
      onValueChange={setModel}
      disabled={isEmpty || !selectedProvider}
    >
      <SelectTrigger className={cn("w-full", className)} aria-invalid={isEmpty}>
        <SelectValue placeholder="Select model" />
      </SelectTrigger>
      <SelectContent>
        {modelOptions.map((m) => (
          <SelectItem key={m.id} value={m.id}>
            {m.id}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
  {
  }
}

export function FieldSelect({ className }: { className?: string }) {
  const status = useSelectionStatus();
  const selectedModel = useSelectedModel();
  const selectedField = useSelectedField();
  const fieldOptions = useFieldOptions();
  const { setField } = useSelectionActions();

  if (status === "loading") return <Skeleton className="h-9 w-full" />;
  if (status === "error")
    return <ErrorStub className={className} placeholder="Unavailable" />;

  const isEmpty = fieldOptions.length === 0;

  return (
    <Select
      value={selectedField ?? ""}
      onValueChange={setField}
      disabled={isEmpty || !selectedModel}
    >
      <SelectTrigger className={cn("w-full", className)} aria-invalid={isEmpty}>
        <SelectValue placeholder="Select field" />
      </SelectTrigger>
      <SelectContent>
        {fieldOptions.map((f) => (
          <SelectItem key={f.id} value={f.id}>
            {formatFieldLabel(f)}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}
