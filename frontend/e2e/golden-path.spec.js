// Golden path: sign in → upload two CPSE files → watch processing → approve a match → see its national code.
// Run against a running stack (docker compose up) on a fresh database:
//   npx playwright install chromium        (once)
//   E2E_BASE_URL=http://localhost:8080 npm run test:e2e
// The sample files use fixed codes, so on a second run the rows are "unchanged" and there may be nothing left to approve.
import { test, expect } from "@playwright/test";
import path from "node:path";
import { fileURLToPath } from "node:url";

const EMAIL = process.env.E2E_EMAIL ?? "admin@ekcode.local";
const PASSWORD = process.env.E2E_PASSWORD ?? "ChangeMe@2026";
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");

test.setTimeout(10 * 60_000); // the first upload downloads the embedding model

test("upload, review, approve, national code", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(EMAIL);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: /Namaste/ })).toBeVisible();

  for (const [cpse, file] of [["IOCL", "test_upload_IOCL.csv"], ["ONGC", "test_upload_ONGC.csv"]]) {
    await page.goto("/ingest");
    await page.getByLabel("CPSE this file belongs to").selectOption(cpse);
    await page.getByLabel("Material export file").setInputFiles(path.join(ROOT, file));
    await expect(page.getByRole("heading", { name: "Check the columns" })).toBeVisible();
    await page.getByRole("button", { name: /Start processing/ }).click();
    await expect(page.getByText(/is processed/)).toBeVisible({ timeout: 8 * 60_000 });
  }

  await page.goto("/review");
  await expect(page.getByText(/Pair #\d+/)).toBeVisible();
  await page.keyboard.press("a");
  const toast = page.getByText(/Approved · /);
  await expect(toast).toBeVisible({ timeout: 30_000 });
  const nmc = (await toast.textContent()).match(/NMC-\d{4}-\d{6}-\d/)?.[0];
  expect(nmc).toBeTruthy();

  await page.goto(`/materials/${nmc}`);
  await expect(page.getByText("check digit valid")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Legacy codes mapped to this NMC" })).toBeVisible();
});
