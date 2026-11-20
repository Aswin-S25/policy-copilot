import { describe, expect, it } from "vitest";
import { demoPersonaName, documentRoles, parseToken, TokenError } from "./session";

const b64url = (value: unknown) =>
  Buffer.from(JSON.stringify(value)).toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

function jwt(claims: Record<string, unknown>) {
  return `${b64url({ alg: "HS256", typ: "JWT" })}.${b64url(claims)}.signature`;
}

const future = Math.floor(Date.now() / 1000) + 3600;

describe("parseToken", () => {
  it("reads subject, roles and expiry for display", () => {
    const session = parseToken(jwt({ sub: "alice", roles: ["employee", "admin"], exp: future }));
    expect(session.subject).toBe("alice");
    expect(session.roles).toEqual(["employee", "admin"]);
    expect(session.expiresAt).toBe(future * 1000);
    expect(documentRoles(session)).toEqual(["employee"]); // admin grants no documents
  });

  it("accepts a pasted 'Bearer ' prefix and surrounding whitespace", () => {
    const token = jwt({ sub: "alice", roles: [], exp: future });
    expect(parseToken(`  Bearer ${token}\n`).token).toBe(token);
  });

  it.each([
    ["not three parts", "abc.def"],
    ["unreadable payload", "a.%%%.c"],
    ["no subject", jwt({ roles: ["employee"], exp: future })],
    ["roles not a list", jwt({ sub: "a", roles: "employee", exp: future })],
    ["no expiry", jwt({ sub: "a", roles: ["employee"] })],
    ["expired", jwt({ sub: "a", roles: ["employee"], exp: 1 })],
  ])("rejects a token with %s", (_reason, token) => {
    expect(() => parseToken(token)).toThrow(TokenError);
  });
});

describe("demoPersonaName", () => {
  const session = (subject: string) => ({ token: "t", subject, roles: [], expiresAt: 0 });

  it("names demo sessions by persona and ignores real accounts", () => {
    expect(demoPersonaName(session("demo-hr-1a2b3c4d"))).toBe("HR");
    expect(demoPersonaName(session("demo-security-00ff00ff"))).toBe("Security");
    expect(demoPersonaName(session("alice"))).toBeNull();
    expect(demoPersonaName(session("demo-hr"))).toBeNull();
  });
});
