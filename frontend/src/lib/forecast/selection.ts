import type {
  AvailableRunsResponse,
  FieldMeta,
  ModelInfo,
  ProviderInfo,
} from "@/api/forecasts";

export type DataSelection = {
  provider: string | null;
  model: string | null;
  field: string | null;
};

export const EMPTY_SELECTION: DataSelection = {
  provider: null,
  model: null,
  field: null,
};

export function findCombo(
  data: AvailableRunsResponse,
  providerId: string,
  modelId: string,
  fieldId: string,
): DataSelection | null {
  const provider = data.providers.find((p) => p.id === providerId);
  const model = provider?.models.find((m) => m.id === modelId);
  const field = model?.fields.find((f) => f.id === fieldId);

  return field
    ? { provider: providerId, model: modelId, field: fieldId }
    : null;
}

export function firstCombo(data: AvailableRunsResponse): DataSelection | null {
  const provider = data.providers[0];
  const model = provider?.models[0];
  const field = model?.fields[0];

  if (!provider || !model || !field) return null;
  return { provider: provider.id, model: model.id, field: field.id };
}

// resolvers: apply field-preserve UX when switching dims

/**
 * Switch provider. Try to preserve field across models under new provider.
 * If no model under new provider has the field, clear model + field.
 */
export function resolveProvider(
  data: AvailableRunsResponse,
  providerId: string,
  preferredFieldId: string | null,
): DataSelection {
  const provider = data.providers.find((p) => p.id === providerId);
  if (!provider) return EMPTY_SELECTION;

  if (preferredFieldId) {
    const foundModel = provider.models.find((m) =>
      m.fields.some((field) => field.id === preferredFieldId),
    );

    if (foundModel)
      return {
        provider: providerId,
        model: foundModel.id,
        field: preferredFieldId,
      };
  }

  return { provider: providerId, model: null, field: null };
}

/**
 * Switch model under existing provider. Keep field if new model has it,
 * else clear field only.
 */
export function resolveModel(
  data: AvailableRunsResponse,
  providerId: string,
  modelId: string,
  preferredFieldId: string | null,
): DataSelection {
  const provider = data.providers.find((p) => p.id === providerId);
  const model = provider?.models.find((m) => m.id === modelId);
  if (!provider || !model) {
    return { provider: providerId, model: null, field: null };
  }

  const keepField =
    preferredFieldId && model.fields.some((f) => f.id === preferredFieldId);

  return {
    provider: providerId,
    model: modelId,
    field: keepField ? preferredFieldId : null,
  };
}

/**
 * Set field on current provider+model. Dropdown should only offer fields
 * valid for the current model, so no search needed.
 */
export function resolveField(
  current: DataSelection,
  fieldId: string,
): DataSelection {
  return { ...current, field: fieldId };
}

// derived option lists for dropdowns

export function availableProviders(
  data: AvailableRunsResponse,
): ProviderInfo[] {
  return data.providers;
}

export function availableModels(
  data: AvailableRunsResponse,
  providerId: string | null,
): ModelInfo[] {
  if (!providerId) return [];
  return data.providers.find((p) => p.id === providerId)?.models ?? [];
}

export function availableFields(
  data: AvailableRunsResponse,
  providerId: string | null,
  modelId: string | null,
) {
  if (!providerId || !modelId) return [];
  const provider = data.providers.find((p) => p.id === providerId);
  return provider?.models.find((m) => m.id === modelId)?.fields ?? [];
}

/**
 * Resolve the selected field id to its full FieldMeta against current data.
 * Returns null if data missing or any selection dim is unset / not found.
 */
export function selectedField(
  data: AvailableRunsResponse | null,
  selection: DataSelection,
): FieldMeta | null {
  const { provider, model, field } = selection;
  if (!data || !provider || !model || !field) return null;
  return (
    availableFields(data, provider, model).find((f) => f.id === field) ?? null
  );
}
