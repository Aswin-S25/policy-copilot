/**
 * Thin fetch wrapper: base URL, bearer token, typed errors, and one global
 * hook for 401 so an expired session signs the user out wherever it happens.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "/api").replace(/\/$/, "");

export function apiUrl(path: string): string {
  return `${BASE_URL}${path}`;
}

export class ApiError extends Error {
  /** HTTP status, or 0 when the server could not be reached. */
  readonly status: number;
  /** Seconds from the Retry-After header (429 rate limit, 503 busy). */
  readonly retryAfter?: number;

  constructor(status: number, message: string, retryAfter?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.retryAfter = retryAfter;
  }
}

export function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}

let currentToken: string | null = null;
let onUnauthorized: (() => void) | null = null;

/** Called by the auth provider; the token never leaves this module otherwise. */
export function configureAuth(token: string | null, unauthorized: (() => void) | null) {
  currentToken = token;
  onUnauthorized = unauthorized;
}

const FALLBACK_MESSAGES: Record<number, string> = {
  0: "Can't reach Policy Copilot. Check your connection and that the service is running.",
  401: "Your session has expired. Sign in again to continue.",
  403: "Your account doesn't have permission to do that.",
  404: "That item doesn't exist or isn't available to you.",
  429: "You've asked too many questions in a short time. Wait a moment and try again.",
  500: "Policy Copilot hit an unexpected error. Try again.",
  503: "The answer service is temporarily unavailable. Try again shortly.",
};

function fallbackMessage(status: number): string {
  return FALLBACK_MESSAGES[status] ?? FALLBACK_MESSAGES[500]!;
}

/** FastAPI errors are {detail: string} or, for validation, {detail: [{msg}]}. */
async function errorFromResponse(response: Response): Promise<ApiError> {
  let message = fallbackMessage(response.status);
  try {
    const body = await response.json();
    if (typeof body?.detail === "string" && response.status !== 500) {
      message = body.detail.trim();
    } else if (Array.isArray(body?.detail) && body.detail[0]?.msg) {
      message = String(body.detail[0].msg);
    }
  } catch {
    // Non-JSON body (proxy error page): keep the fallback message.
  }
  const retryHeader = Number(response.headers.get("Retry-After"));
  const retryAfter = Number.isFinite(retryHeader) && retryHeader > 0 ? retryHeader : undefined;
  return new ApiError(response.status, message, retryAfter);
}

export interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  body?: unknown;
  signal?: AbortSignal;
  accept?: string;
  /** Use a specific token instead of the session's (sign-in verification). */
  token?: string;
}

/** Performs the request and returns the raw Response if it was 2xx. */
export async function request(path: string, options: RequestOptions = {}): Promise<Response> {
  const token = options.token ?? currentToken;
  const headers: Record<string, string> = { Accept: options.accept ?? "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  if (options.body !== undefined) headers["Content-Type"] = "application/json";

  let response: Response;
  try {
    response = await fetch(apiUrl(path), {
      method: options.method ?? "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
      cache: "no-store",
    });
  } catch (error) {
    if (isAbortError(error)) throw error;
    throw new ApiError(0, fallbackMessage(0));
  }

  if (!response.ok) {
    const error = await errorFromResponse(response);
    // A rejected session token means the session is over. A token being
    // verified at sign-in is not the session yet, so it is left alone.
    if (response.status === 401 && options.token === undefined) {
      onUnauthorized?.();
      throw new ApiError(401, fallbackMessage(401));
    }
    throw error;
  }
  return response;
}

export async function requestJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await request(path, options);
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}
