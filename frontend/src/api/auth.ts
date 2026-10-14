import { getJson, postJson, setAuthToken } from "./client";

export interface SessionUser {
  id: number;
  email: string;
}

export interface SessionOrganization {
  id: number;
  name: string;
  slug: string;
}

export interface MeResponse {
  user: SessionUser;
  organization: SessionOrganization;
}

export interface CreatedApiKey {
  id: number;
  name: string;
  key: string;
  prefix: string;
}

export interface SessionResponse {
  access_token: string;
  token_type: string;
  organization: SessionOrganization;
  email: string;
}

export interface RegisterResponse {
  access_token: string;
  organization: SessionOrganization;
  email: string;
  api_key: CreatedApiKey;
}

export function fetchMe(): Promise<MeResponse> {
  return getJson<MeResponse>("/api/auth/me");
}

export async function login(email: string, password: string): Promise<SessionResponse> {
  const data = await postJson<SessionResponse>("/api/auth/login", { email, password });
  if (data?.access_token) {
    setAuthToken(data.access_token);
  }
  return data;
}

export async function register(organizationName: string, email: string, password: string): Promise<RegisterResponse> {
  const res = await postJson<RegisterResponse>("/api/auth/register", {
    organization_name: organizationName,
    email,
    password,
  });
  if (res?.access_token) {
    setAuthToken(res.access_token);
  }
  return res;
}

export async function logout(): Promise<unknown> {
  try {
    return await postJson("/api/auth/logout", {});
  } finally {
    setAuthToken(null);
  }
}
