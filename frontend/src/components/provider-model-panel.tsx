import { useState } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";

type ModelOption = {
  id: string;
  label: string;
  fields: string[];
};

type ProviderOption = {
  id: string;
  label: string;
  models: ModelOption[];
};

// TODO: format to api requests
const PROVIDERS: ProviderOption[] = [
  {
    id: "nomads",
    label: "NOMADS",
    models: [
      {
        id: "nwps",
        label: "NWPS (Nearshore Wave Prediction)",
        fields: ["swh", "perpw", "dirpw", "wind_u", "wind_v"],
      },
    ],
  },
  {
    id: "pacioos",
    label: "PacIOOS",
    models: [],
  },
];

const DEFAULT_PROVIDER_ID = "nomads";
const DEFAULT_MODEL_ID = "nwps";

export type ProviderModelSelection = {
  providerId: string;
  modelId: string;
  fieldId: string | null;
};

type ProviderModelPanelProps = {
  className?: string;
  onSelectionChange?: (selection: ProviderModelSelection) => void;
};

export function ProviderModelPanel({
  className,
  onSelectionChange,
}: ProviderModelPanelProps) {
  const [providerId, setProviderId] = useState<string>(DEFAULT_PROVIDER_ID);
  const [modelId, setModelId] = useState<string>(DEFAULT_MODEL_ID);
  const [fieldId, setFieldId] = useState<string | null>(null);

  const provider = PROVIDERS.find((p) => p.id === providerId);
  const model = provider?.models.find((m) => m.id === modelId);

  const emit = (next: ProviderModelSelection) => onSelectionChange?.(next);

  const handleProviderChange = (nextProviderId: string) => {
    const nextProvider = PROVIDERS.find((p) => p.id === nextProviderId);
    if (!nextProvider) return;
    const nextModelId = nextProvider.models[0]?.id ?? "";
    setProviderId(nextProviderId);
    setModelId(nextModelId);
    setFieldId(null);
    emit({ providerId: nextProviderId, modelId: nextModelId, fieldId: null });
  };

  const handleModelChange = (nextModelId: string) => {
    setModelId(nextModelId);
    setFieldId(null);
    emit({ providerId, modelId: nextModelId, fieldId: null });
  };

  const handleFieldChange = (nextFieldId: string) => {
    setFieldId(nextFieldId);
    emit({ providerId, modelId, fieldId: nextFieldId });
  };

  return (
    <Card className={cn("w-72", className)}>
      <CardHeader>
        <CardTitle>Data Source</CardTitle>
        <CardDescription>Provider · Model · Field</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium">Provider</label>
          <Select value={providerId} onValueChange={handleProviderChange}>
            <SelectTrigger>
              <SelectValue placeholder="Select provider" />
            </SelectTrigger>
            <SelectContent>
              {PROVIDERS.map((p) => (
                <SelectItem key={p.id} value={p.id}>
                  {p.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium">Model</label>
          <Select
            value={modelId}
            onValueChange={handleModelChange}
            disabled={!provider}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select model" />
            </SelectTrigger>
            <SelectContent>
              {provider?.models.map((m) => (
                <SelectItem key={m.id} value={m.id}>
                  {m.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="flex flex-col gap-1.5">
          <label className="text-xs font-medium">Field</label>
          <Select
            value={fieldId ?? ""}
            onValueChange={handleFieldChange}
            disabled={!model}
          >
            <SelectTrigger>
              <SelectValue placeholder="Select field" />
            </SelectTrigger>
            <SelectContent>
              {model?.fields.map((f) => (
                <SelectItem key={f} value={f}>
                  {f}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </CardContent>
    </Card>
  );
}
