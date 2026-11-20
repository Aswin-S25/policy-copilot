import { expect, test, type Page } from "@playwright/test";

/*
  Real-stack journeys. Model wording varies run to run, so assertions check
  structure (an answer, citations, a quoted passage) rather than exact text.
*/

test.describe.configure({ mode: "serial" });

const employeeToken = () => process.env.E2E_EMPLOYEE_TOKEN!;
const securityToken = () => process.env.E2E_SECURITY_TOKEN!;

// From eval/datasets/golden.json: answerable for the employee role.
const QUESTION = "How many days of annual leave do employees get?";
const FOLLOW_UP = "Can unused days be carried over to next year?";

let conversationUrl = "";

async function signIn(page: Page, token: string) {
  await page.goto("/login");
  await page.getByLabel("Access token").fill(token);
  await expect(page.getByText("Signs in as")).toBeVisible();
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Ask about a company policy" })).toBeVisible();
}

async function waitForAnswer(page: Page) {
  // The Send button returns once the turn is saved and reloaded.
  await expect(page.getByRole("button", { name: "Send question" })).toBeVisible({ timeout: 150_000 });
}

test("rejects a malformed token, then signs in with a real one", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("Access token").fill("not-a-token");
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("alert")).toContainText("isn't an access token");

  await page.getByLabel("Access token").fill(employeeToken());
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByText("Searching documents shared with")).toContainText("Employee");
});

test("streams a cited answer, opens a source passage, and keeps citations after reload", async ({ page }) => {
  await signIn(page, employeeToken());

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
  await signIn(page, employeeToken());
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
  const accessFor = async (token: string) => {
    const page = await browser.newPage();
    await signIn(page, token);
    await page.getByRole("link", { name: "Policy documents" }).click();
    await expect(page.getByText(/^\d+ documents?$/)).toBeVisible();
    const cells = await page.locator("tbody tr td:nth-child(2)").allInnerTexts();
    await page.close();
    return cells.map((cell) => cell.replace("Your access:", "").trim());
  };

  const employee = await accessFor(employeeToken());
  const security = await accessFor(securityToken());
  expect(employee.length).toBeGreaterThan(0);
  expect(security.length).toBeGreaterThan(0);
  // Each user sees only their own granting role, never other roles on the ACL.
  expect(employee.every((access) => access === "Employee")).toBe(true);
  expect(security.every((access) => access === "Security")).toBe(true);
});

test("another user can't open this conversation", async ({ page }) => {
  await signIn(page, securityToken());
  await page.goto(conversationUrl);
  await expect(page.getByRole("heading", { name: "This conversation isn't available" })).toBeVisible();
});

test("deletes the conversation", async ({ page }) => {
  await signIn(page, employeeToken());
  await page.goto(conversationUrl);
  await page.getByRole("button", { name: "Delete conversation" }).click();
  const dialog = page.getByRole("dialog", { name: "Delete conversation?" });
  await dialog.getByRole("button", { name: "Delete" }).click();
  await expect(page).toHaveURL(/\/$/);

  await page.goto(conversationUrl);
  await expect(page.getByRole("heading", { name: "This conversation isn't available" })).toBeVisible();
});

test("a token the API rejects ends the session", async ({ page }) => {
  // Well-formed and unexpired, but not signed by this API: the server's 401
  // must sign the user out, not just the client-side expiry check.
  const [header, payload] = employeeToken().split(".");
  await page.addInitScript(
    (forged) => sessionStorage.setItem("policy-copilot.session", forged),
    `${header}.${payload}.invalid-signature`,
  );
  await page.goto("/");
  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByText("Your session expired")).toBeVisible();
});
