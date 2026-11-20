import { requestJson } from "./client";

/** POST /auth/login (app/api/auth.py). */
export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  /** Seconds until the token expires. */
  expires_in: number;
}

/** 401: wrong credentials. 429: too many attempts (ApiError.retryAfter). */
export function login(username: string, password: string) {
  return requestJson<LoginResponse>("/auth/login", {
    method: "POST",
    body: { username, password },
    anonymous: true,
  });
}
