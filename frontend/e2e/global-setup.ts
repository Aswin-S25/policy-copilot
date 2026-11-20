import { execFileSync } from "node:child_process";
import { randomBytes } from "node:crypto";
import path from "node:path";

export const REPO_ROOT = path.resolve(import.meta.dirname, "../..");
const API = process.env.API_PROXY_TARGET ?? "http://127.0.0.1:8000";

/** Runs the project's account CLI (app/cli/users.py) from the repository root. */
export function usersCli(args: string[], stdin?: string): string {
  return execFileSync(process.env.PYTHON ?? "python", ["-m", "app.cli.users", ...args], {
    cwd: REPO_ROOT,
    encoding: "utf8",
    input: stdin,
  }).trim();
}

/**
 * Creates two throwaway accounts (employee, security) with random passwords,
 * so tests sign in through the real form and /auth/login. Credentials live
 * only in this process's environment; global-teardown deletes the accounts.
 */
export default async function globalSetup() {
  const ready = await fetch(`${API}/health/ready`).catch(() => null);
  if (!ready?.ok) {
    throw new Error(
      `The API at ${API} isn't ready. Start it with "docker compose up -d" (and Ollama) before running E2E tests.`,
    );
  }

  const run = Date.now().toString(36);
  const accounts = { EMPLOYEE: "employee", SECURITY: "security" } as const;
  for (const [key, role] of Object.entries(accounts)) {
    const username = `e2e-${role}-${run}`;
    const password = randomBytes(18).toString("base64url");
    usersCli(["create", username, "--roles", role, "--password-stdin"], `${password}\n`);
    process.env[`E2E_${key}_USERNAME`] = username;
    process.env[`E2E_${key}_PASSWORD`] = password;
  }
}
