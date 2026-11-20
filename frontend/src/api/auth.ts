import { requestJson } from "./client";

/** POST /auth/login and POST /auth/demo (app/api/auth.py). */
export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  /** Seconds until the token expires. */
  expires_in: number;
}

export interface DemoPersona {
  id: "employee" | "manager" | "hr" | "security";
  label: string;
  roles: string[];
  /** Documents this persona can read: the demo's point is that it differs. */
  document_count: number;
}

/** GET /auth/options: `demo` is null unless the server runs in demo mode. */
export interface SignInOptions {
  demo: { personas: DemoPersona[] } | null;
}

/** 401: wrong credentials. 429: too many attempts (ApiError.retryAfter). */
export function login(username: string, password: string) {
  return requestJson<LoginResponse>("/auth/login", {
    method: "POST",
    body: { username, password },
    anonymous: true,
  });
}

export function getSignInOptions(signal?: AbortSignal) {
  return requestJson<SignInOptions>("/auth/options", { signal, anonymous: true });
}

/** A fresh, private demo identity with the persona's roles. */
export function demoSignIn(persona: DemoPersona["id"]) {
  return requestJson<LoginResponse>("/auth/demo", {
    method: "POST",
    body: { persona },
    anonymous: true,
  });
}
