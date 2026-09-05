const API_BASE = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  code: string;
  requestId: string;
  details: unknown;

  constructor(code: string, message: string, requestId: string, details?: unknown) {
    super(message);
    this.code = code;
    this.requestId = requestId;
    this.details = details;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const token = localStorage.getItem("revpilot_access_token");
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init?.headers,
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const err = body?.error;
    throw new ApiError(
      err?.code ?? "UNKNOWN_ERROR",
      err?.message ?? `Request failed with status ${response.status}`,
      err?.request_id ?? "unknown",
      err?.details,
    );
  }

  return response.json() as Promise<T>;
}

// Separate from apiFetch on purpose: file uploads must NOT set
// Content-Type manually — the browser needs to generate the multipart
// boundary itself. apiFetch always forces "application/json", which
// would corrupt a FormData upload if reused here.
export async function apiUpload<T>(path: string, file: File): Promise<T> {
  const token = localStorage.getItem("revpilot_access_token");
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    body: formData,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const err = body?.error;
    throw new ApiError(
      err?.code ?? "UNKNOWN_ERROR",
      err?.message ?? `Upload failed with status ${response.status}`,
      err?.request_id ?? "unknown",
      err?.details,
    );
  }

  return response.json() as Promise<T>;
}
