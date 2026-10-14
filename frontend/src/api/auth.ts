import { getJson, postJson } from "./client";

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

export interface RegisterResponse {
  access_token: string;
  organization: SessionOrganization;
  email: string;
  api_key: CreatedApiKey;
}

export function fetchMe(): Promise<MeResponse> {
  return getJson<MeResponse>("/api/auth/me");
}

export function login(email: string, password: string): Promise<unknown> {
  return postJson("/api/auth/login", { email, password });
}

export function register(organizationName: string, email: string, password: string): Promise<RegisterResponse> {
  return postJson<RegisterResponse>("/api/auth/register", {
    organization_name: organizationName,
    email,
    password,
  });
}

export function logout(): Promise<unknown> {
  return postJson("/api/auth/logout", {});
}
