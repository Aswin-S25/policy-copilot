import { execFileSync } from "node:child_process";
import path from "node:path";

const REPO_ROOT = path.resolve(import.meta.dirname, "../..");
const API = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

/**
 * Mints short-lived tokens with the project's own dev CLI
 * (app/cli/issue_token.py), so tests authenticate exactly like a user.
 * Tokens live only in this process's environment; nothing is written to disk.
 * Set E2E_EMPLOYEE_TOKEN / E2E_SECURITY_TOKEN to supply your own instead.
 */
function mint(sub: string, roles: string[]): string {
  return execFileSync(
    process.env.PYTHON ?? "python",
    ["-m", "app.cli.issue_token", "--sub", sub, "--roles", ...roles, "--ttl", "30"],
    { cwd: REPO_ROOT, encoding: "utf8" },
  ).trim();
}

export default async function globalSetup() {
  const ready = await fetch(`${API}/health/ready`).catch(() => null);
  if (!ready?.ok) {
    throw new Error(
      `The API at ${API} isn't ready. Start it with "docker compose up -d" (and Ollama) before running E2E tests.`,
    );
  }

  const run = Date.now().toString(36);
  process.env.E2E_EMPLOYEE_TOKEN ??= mint(`e2e-employee-${run}`, ["employee"]);
  process.env.E2E_SECURITY_TOKEN ??= mint(`e2e-security-${run}`, ["security"]);
}
