const BASE_URL = import.meta.env.VITE_API_BASE_URL;

if (import.meta.env.DEV && !BASE_URL) {
  console.warn(
    "[apiClient] VITE_API_BASE_URL is not set. Requests will fail. " +
      "Copy .env.sample to .env.local and set VITE_API_BASE_URL.",
  );
}

type SuccessResponse<T> = { success: true; data: T; message?: string };
type ErrorResponse = {
  success: false;
  message: string;
  error_code?: string;
  details?: Record<string, unknown>;
};
type ApiResponse<T> = SuccessResponse<T> | ErrorResponse;

export class ApiError extends Error {
  error_code: string;
  details?: Record<string, unknown>;
  status?: number;

  constructor(
    error_code: string,
    message: string,
    details?: Record<string, unknown>,
    status?: number,
  ) {
    super(message);
    this.name = "ApiError";
    this.error_code = error_code;
    this.details = details;
    this.status = status;
  }
}

function devLog(path: string, params: unknown, error: unknown) {
  if (!import.meta.env.DEV) return;
  console.error("[apiFetch]", { path, params, error });
}

export async function apiFetch<T>(
  path: string,
  params?: Record<string, string>,
): Promise<T> {
  const url = new URL(`${BASE_URL}${path}`);
  if (params)
    Object.entries(params).forEach(([k, v]) => url.searchParams.set(k, v));

  let res: Response;
  try {
    res = await fetch(url);
  } catch (err) {
    const error = new ApiError(
      "network_error",
      "Failed to reach API. Check your connection or backend status.",
      { cause: err instanceof Error ? err.message : String(err) },
    );
    devLog(path, params, error);
    throw error;
  }

  let json: ApiResponse<T>;
  try {
    json = await res.json();
  } catch (err) {
    const error = new ApiError(
      "invalid_response",
      `Invalid JSON from API (HTTP ${res.status}).`,
      { cause: err instanceof Error ? err.message : String(err) },
      res.status,
    );
    devLog(path, params, error);
    throw error;
  }

  if (!json.success) {
    const error = new ApiError(
      json.error_code ?? "unknown",
      json.message,
      json.details,
      res.status,
    );
    devLog(path, params, error);
    throw error;
  }

  return json.data as T;
}
