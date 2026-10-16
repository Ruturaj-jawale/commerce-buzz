const apiUrl = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const TOKEN_KEY = "saas_mcp_access_token";

export function setAuthToken(token: string | null): void {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function getAuthToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

function requestHeaders(includeJson = false): HeadersInit {
  const token = getAuthToken();
  return {
    ...(includeJson ? { "Content-Type": "application/json" } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
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
  Object.entries(fields).forEach(([name, value]) => {
    if (value !== undefined && value !== null && value !== "") form.append(name, value);
  });
  const token = getAuthToken();
  const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};
  const response = await fetch(`${getApiUrl()}${path}`, {
    method: "POST",
    headers,
    credentials: "include",
    body: form,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new ApiError(detail || `Request failed: ${response.status}`, response.status);
  }
  return (await response.json()) as T;
}
