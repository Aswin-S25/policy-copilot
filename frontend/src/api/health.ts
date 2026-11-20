import { apiUrl } from "./client";

/**
 * GET /health/ready (app/api/health.py): 200 when ready, 503 with the same
 * body otherwise. Public endpoint; no token is sent. "unreachable" means no
 * response at all (network down, API stopped, proxy error page).
 */
export type ServiceState = "ready" | "warming_up" | "unavailable" | "unreachable";

export async function getServiceState(signal?: AbortSignal): Promise<ServiceState> {
  try {
    const response = await fetch(apiUrl("/health/ready"), { signal, cache: "no-store" });
    const body = (await response.json()) as { status?: string };
    if (body.status === "ready" || body.status === "warming_up" || body.status === "unavailable") {
      return body.status;
    }
    return response.ok ? "ready" : "unavailable";
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") throw error;
    return "unreachable";
  }
}
