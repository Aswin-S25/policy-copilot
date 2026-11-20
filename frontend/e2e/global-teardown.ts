import { usersCli } from "./global-setup";

/** Deletes the accounts created by global-setup, even when tests failed. */
export default async function globalTeardown() {
  for (const key of ["EMPLOYEE", "SECURITY"]) {
    const username = process.env[`E2E_${key}_USERNAME`];
    if (!username) continue;
    try {
      usersCli(["delete", username]);
    } catch (error) {
      console.warn(`Couldn't delete E2E account ${username}:`, error);
    }
  }
}
