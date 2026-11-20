import { expect, test, type Page } from "@playwright/test";

/*
  Real-stack journeys. Model wording varies run to run, so assertions check
  structure (an answer, citations, a quoted passage) rather than exact text.
*/

test.describe.configure({ mode: "serial" });

interface Account {
  username: string;
  password: string;
}
const account = (key: "EMPLOYEE" | "SECURITY"): Account => ({
  username: process.env[`E2E_${key}_USERNAME`]!,
  password: process.env[`E2E_${key}_PASSWORD`]!,
});
const employee = () => account("EMPLOYEE");
const security = () => account("SECURITY");

// From eval/datasets/golden.json: answerable for the employee role.
const QUESTION = "How many days of annual leave do employees get?";
const FOLLOW_UP = "Can unused days be carried over to next year?";

let conversationUrl = "";

async function fillSignIn(page: Page, { username, password }: Account) {
  await page.getByLabel("Username").fill(username);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
}

async function signIn(page: Page, who: Account) {
  await page.goto("/login");
  await fillSignIn(page, who);
  await expect(page.getByRole("heading", { name: "Ask about a company policy" })).toBeVisible();
}

async function waitForAnswer(page: Page) {
  // The Send button returns once the turn is saved and reloaded.
  await expect(page.getByRole("button", { name: "Send question" })).toBeVisible({ timeout: 150_000 });
}

test("rejects a wrong password, then signs in and out", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);

  await fillSignIn(page, { username: employee().username, password: "definitely-not-it" });
  await expect(page.getByRole("alert")).toHaveText("Incorrect username or password.");
  await expect(page.getByLabel("Password", { exact: true })).toHaveValue(""); // cleared for retry

  await fillSignIn(page, employee());
  await expect(page.getByText("Searching documents shared with")).toContainText("Employee");
  await expect(page.getByText(employee().username, { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/); // the session is really gone
});

test("streams a cited answer, opens a source passage, and keeps citations after reload", async ({ page }) => {
  await signIn(page, employee());

  const composer = page.locator("#composer-input");
  await composer.fill(QUESTION);
  await composer.press("Enter");
  await expect(page).toHaveURL(/\/c\/[0-9a-f-]{36}$/);
  conversationUrl = page.url();

  await expect(page.getByRole("button", { name: "Stop generating" })).toBeVisible();
  await waitForAnswer(page);

  // Exactly one copy of the question; an answer with clickable citations.
  await expect(page.locator(".space-y-7").getByText(QUESTION, { exact: true })).toHaveCount(1);
  const markers = page.locator("button.cite");
  await expect(markers.first()).toBeVisible();

  await markers.first().click();
  const panel = page.getByRole("complementary", { name: "Sources" });
  await expect(panel.getByText("Cited in this answer")).toBeVisible();
  const passage = panel.locator(".passage-active");
  await expect(passage).toBeVisible();
  await expect(passage).not.toBeEmpty();
  await expect(panel.getByText("Quoted policy text")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();

  // History comes back from GET /conversations/{id} with citations attached.
  await page.reload();
  await expect(page.locator("button.cite").first()).toBeVisible();
  await expect(page.getByRole("link", { name: QUESTION })).toBeVisible();
});

test("answers a follow-up in the same conversation", async ({ page }) => {
  await signIn(page, employee());
  await page.goto(conversationUrl);
  await expect(page.locator("button.cite").first()).toBeVisible();

  const composer = page.locator("#composer-input");
  await composer.fill(FOLLOW_UP);
  await composer.press("Enter");
  await waitForAnswer(page);

  const thread = page.locator(".space-y-7");
  await expect(thread.getByText(QUESTION, { exact: true })).toHaveCount(1);
  await expect(thread.getByText(FOLLOW_UP, { exact: true })).toHaveCount(1);
  await expect(thread.locator(".answer-prose")).toHaveCount(2);
});

test("lists only documents the role can read", async ({ browser }) => {
  // The "Your access" cell of each row (titles may contain role words).
  const accessFor = async (who: Account) => {
    const page = await browser.newPage();
    await signIn(page, who);
    await page.getByRole("link", { name: "Policy documents" }).click();
    await expect(page.getByText(/^\d+ documents?$/)).toBeVisible();
    const cells = await page.locator("tbody tr td:nth-child(2)").allInnerTexts();
    await page.close();
    return cells.map((cell) => cell.replace("Your access:", "").trim());
  };

  const employeeAccess = await accessFor(employee());
  const securityAccess = await accessFor(security());
  expect(employeeAccess.length).toBeGreaterThan(0);
  expect(securityAccess.length).toBeGreaterThan(0);
  // Each user sees only their own granting role, never other roles on the ACL.
  expect(employeeAccess.every((access) => access === "Employee")).toBe(true);
  expect(securityAccess.every((access) => access === "Security")).toBe(true);
});

test("another user can't open this conversation", async ({ page }) => {
  await signIn(page, security());
  await page.goto(conversationUrl);
  await expect(page.getByRole("heading", { name: "This conversation isn't available" })).toBeVisible();
});

test("deletes the conversation", async ({ page }) => {
  await signIn(page, employee());
  await page.goto(conversationUrl);
  await page.getByRole("button", { name: "Delete conversation" }).click();
  const dialog = page.getByRole("dialog", { name: "Delete conversation?" });
  await dialog.getByRole("button", { name: "Delete" }).click();
  await expect(page).toHaveURL(/\/$/);

  await page.goto(conversationUrl);
  await expect(page.getByRole("heading", { name: "This conversation isn't available" })).toBeVisible();
});

test("demo sign-in shows each role its own documents", async ({ page, request }) => {
  const options = await (await request.get("/api/auth/options")).json();
  test.skip(!options.demo, "Demo mode is off (POLICY_DEMO_MODE)");

  const documentsAs = async (role: string) => {
    await page.goto("/login");
    await page.getByRole("button", { name: new RegExp(`^${role}`) }).click();
    await expect(page.getByText(`${role} (demo)`)).toBeVisible();
    await page.getByRole("link", { name: "Policy documents" }).click();
    await expect(page.getByText(/^\d+ documents?$/)).toBeVisible();
    const count = await page.locator("tbody tr").count();
    await page.getByRole("button", { name: "Sign out to switch role" }).click();
    await expect(page).toHaveURL(/\/login$/);
    return count;
  };

  const personas: { label: string; document_count: number }[] = options.demo.personas;
  for (const label of ["Employee", "Security"]) {
    const expected = personas.find((p) => p.label === label)!.document_count;
    expect(await documentsAs(label)).toBe(expected);
  }
});

test("a token the API rejects ends the session", async ({ page }) => {
  // Well-formed and unexpired, but not signed by this API: the server's 401
  // must sign the user out, not just the client-side expiry check.
  const b64 = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  const exp = Math.floor(Date.now() / 1000) + 3600;
  const forged = `${b64({ alg: "HS256", typ: "JWT" })}.${b64({ sub: "mallory", roles: ["employee"], exp })}.bad-signature`;
  await page.addInitScript((token) => sessionStorage.setItem("policy-copilot.session", token), forged);
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText("Your session expired")).toBeVisible();
});
