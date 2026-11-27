import { apiUrl } from "./client";
import { ensureAwake, noteApiResponse } from "./wake";

/**
 * GET /health/ready (app/api/health.py): 200 when ready, 503 with the same
 * body otherwise. Public endpoint; no token is sent. "unreachable" means no
 * response at all (network down, API stopped, proxy error page).
 */
export type ServiceState = "ready" | "warming_up" | "unavailable" | "unreachable";

export async function getServiceState(signal?: AbortSignal): Promise<ServiceState> {
  try {
    await ensureAwake(); // a sleeping free-tier API is waking, not broken
    const response = await fetch(apiUrl("/health/ready"), { signal, cache: "no-store" });
    noteApiResponse();
    const body = (await response.json()) as { status?: string };
    if (body.status === "ready" || body.status === "warming_up" || body.status === "unavailable") {
      return body.status;
    }
    return response.ok ? "ready" : "unavailable";
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    return "unreachable"; // includes WakeTimeoutError: it never woke up
  }
}
