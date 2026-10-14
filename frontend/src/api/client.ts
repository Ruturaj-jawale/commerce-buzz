const apiUrl = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

function requestHeaders(includeJson = false): HeadersInit {
  return {
    ...(includeJson ? { "Content-Type": "application/json" } : {}),
  };
}

export function getApiUrl(): string {
  return apiUrl.replace(/\/$/, "");
}

export async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${getApiUrl()}${path}`, {
    headers: requestHeaders(),
    credentials: "include",
  });
  if (!response.ok) {
    throw new ApiError(`Request failed: ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${getApiUrl()}${path}`, {
    method: "POST",
    headers: requestHeaders(true),
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(detail || `Request failed: ${response.status}`, response.status);
  }
  const text = await response.text();
  return (text ? (JSON.parse(text) as T) : (null as T));
}

export async function putJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${getApiUrl()}${path}`, {
    method: "PUT",
    headers: requestHeaders(true),
    credentials: "include",
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(detail || `Request failed: ${response.status}`, response.status);
  }
  const text = await response.text();
  return (text ? (JSON.parse(text) as T) : (null as T));
}

export async function uploadFile<T>(path: string, file: File, fields: Record<string, string> = {}): Promise<T> {
  const form = new FormData();
  form.append("file", file);
  Object.entries(fields).forEach(([name, value]) => form.append(name, value));
  const response = await fetch(`${getApiUrl()}${path}`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(detail || `Request failed: ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}
