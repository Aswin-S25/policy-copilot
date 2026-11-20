/**
 * Session = the bearer token plus claims decoded for display.
 *
 * Claims are decoded here only to show who is signed in and when the
 * session ends. The browser cannot verify the signature; the API verifies
 * every request and is the only authority on whether a token is valid.
 *
 * Stored in sessionStorage: survives a reload, cleared when the tab closes,
 * never shared with other tabs, never put in URLs or logs.
 */

export interface Session {
  token: string;
  subject: string;
  roles: string[];
  /** Epoch milliseconds. */
  expiresAt: number;
}

const STORAGE_KEY = "policy-copilot.session";

/** Roles that grant document access (app/core/authz.py ROLES). "admin" only grants ingestion. */
export const DOCUMENT_ROLES = ["employee", "manager", "hr", "security"] as const;

const ROLE_NAMES: Record<string, string> = {
  employee: "Employee",
  manager: "Manager",
  hr: "HR",
  security: "Security",
  admin: "Admin",
};

export function roleName(role: string): string {
  return ROLE_NAMES[role] ?? role;
}

/**
 * Demo sessions have subjects like "demo-security-1a2b3c4d" (app/api/auth.py;
 * real usernames can't start with "demo-"). Returns the persona's display
 * name, or null for a real account.
 */
export function demoPersonaName(session: Session): string | null {
  const match = /^demo-([a-z]+)-[0-9a-f]+$/.exec(session.subject);
  return match ? roleName(match[1]!) : null;
}

export function documentRoles(session: Session): string[] {
  return session.roles.filter((role) => (DOCUMENT_ROLES as readonly string[]).includes(role));
}

export class TokenError extends Error {}

function decodeBase64Url(segment: string): string {
  const base64 = segment.replace(/-/g, "+").replace(/_/g, "/");
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
  const bytes = Uint8Array.from(atob(padded), (char) => char.charCodeAt(0));
  return new TextDecoder().decode(bytes);
}

export function formatExpiry(expiresAt: number): string {
  const date = new Date(expiresAt);
  const sameDay = date.toDateString() === new Date().toDateString();
  const time = date.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  return sameDay ? `today at ${time}` : `${date.toLocaleDateString([], { month: "short", day: "numeric" })} at ${time}`;
}

/** Reads a pasted token. Throws TokenError with a message the user can act on. */
export function parseToken(raw: string): Session {
  const token = raw.trim().replace(/^Bearer\s+/i, "");
  const parts = token.split(".");
  if (parts.length !== 3 || parts.some((part) => !part)) {
    throw new TokenError(
      "This isn't an access token. A token has three parts separated by dots; copy the whole value.",
    );
  }

  let claims: Record<string, unknown>;
  try {
    claims = JSON.parse(decodeBase64Url(parts[1]!));
  } catch {
    throw new TokenError("This token can't be read. Copy the whole token and paste it again.");
  }

  const { sub, roles, exp } = claims;
  if (typeof sub !== "string" || !sub) {
    throw new TokenError("This token doesn't name a user, so it can't be used here.");
  }
  if (!Array.isArray(roles) || !roles.every((role) => typeof role === "string")) {
    throw new TokenError("This token doesn't list any roles, so it can't be used here.");
  }
  if (typeof exp !== "number") {
    throw new TokenError("This token has no expiry time, so it can't be used here.");
  }

  const expiresAt = exp * 1000;
  if (expiresAt <= Date.now()) {
    throw new TokenError(`This token expired ${formatExpiry(expiresAt)}. Get a new token and try again.`);
  }

  return { token, subject: sub, roles: roles as string[], expiresAt };
}

/** Returns the stored session if it is still within its lifetime. */
export function loadSession(): { session: Session | null; expired: boolean } {
  let raw: string | null = null;
  try {
    raw = sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return { session: null, expired: false };
  }
  if (!raw) return { session: null, expired: false };

  try {
    return { session: parseToken(raw), expired: false };
  } catch {
    clearSession();
    return { session: null, expired: true };
  }
}

export function saveSession(session: Session) {
  try {
    sessionStorage.setItem(STORAGE_KEY, session.token);
  } catch {
    // Storage blocked (private mode policies): the session lasts until reload.
  }
}

export function clearSession() {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    // Nothing stored.
  }
}
