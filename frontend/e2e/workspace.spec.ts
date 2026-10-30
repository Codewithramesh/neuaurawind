import { test, expect } from "@playwright/test";
import path from "node:path";
const screenshotDir = path.resolve(
  import.meta.dirname,
  "../../local-data/verification",
);
async function signIn(page: any) {
  await page.goto("/");
  await page.getByLabel("Email", { exact: true }).fill("browser@example.test");
  await page
    .getByLabel("Password", { exact: true })
    .fill("browser-test-password");
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "A clearer picture." }),
  ).toBeVisible();
}
test("empty dashboard, real MediaRecorder transport, TEST DOUBLE intelligence, evidence, task approval", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await signIn(page);
  await expect(page.getByText("Your next insight starts here.")).toBeVisible();
  await page.screenshot({
    path: path.join(screenshotDir, "dashboard-desktop.png"),
    fullPage: true,
  });
  await page
    .getByRole("button", { name: "New conversation", exact: true })
    .click();
  const dialog = page.getByRole("dialog");
  await expect(
    dialog.getByRole("button", { name: "Start recording" }),
  ).toHaveCount(0);
  await dialog
    .getByLabel("Conversation title")
    .fill("TEST ONLY browser microphone pipeline");
  await dialog
    .getByLabel("Session purpose")
    .fill("TEST ONLY consent and capture verification");
  await dialog.getByLabel("Participant references").fill("TEST participant");
  await dialog.getByRole("button", { name: "Prepare session" }).click();
  await dialog
    .getByRole("button", { name: "Participant review", exact: true })
    .click();
  await dialog.locator(".participant-notice").getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "I agree for myself" }).click();
  await dialog
    .getByRole("button", { name: "Return to operator controls" })
    .click();
  await dialog.getByRole("checkbox").check();
  await dialog
    .getByRole("button", { name: "Validate consent and prepare capture" })
    .click();
  await dialog.getByRole("button", { name: "Start recording" }).click();
  await expect(dialog.getByText("RECORDING", { exact: true })).toBeVisible();
  await page.waitForTimeout(2200);
  await dialog.getByRole("button", { name: "Pause", exact: true }).click();
  await expect(dialog.getByText("PAUSED", { exact: true })).toBeVisible();
  await dialog.getByRole("checkbox").check();
  await dialog.getByRole("button", { name: "Resume", exact: true }).click();
  await page.waitForTimeout(800);
  await dialog.getByRole("button", { name: "Stop recording" }).click();
  await expect(dialog.locator("audio")).toBeVisible();
  await dialog.getByRole("button", { name: "Analyze conversation" }).click();
  const detail = page.getByRole("dialog");
  await expect(
    detail.getByRole("heading", {
      name: "TEST ONLY browser microphone pipeline",
    }),
  ).toBeVisible({ timeout: 20000 });
  await expect(detail.getByText("Complete", { exact: true })).toBeVisible({
    timeout: 20000,
  });
  await expect(
    detail.getByText(
      "The coffee was excellent. We waited twenty minutes for our order.",
      { exact: true },
    ),
  ).toBeVisible();
  await detail.locator(".finding-review").getByRole("checkbox").check();
  await detail
    .getByRole("button", { name: "Approve finding", exact: true })
    .click();
  await detail
    .getByRole("button", { name: "Approve session for sharing" })
    .click();
  await detail.getByRole("button", { name: "Approve", exact: true }).click();
  await expect(
    detail.locator(".task-row").getByText("Approved", { exact: true }),
  ).toBeVisible();
  await detail.getByRole("button", { name: "Close conversation" }).click();
  await page
    .getByRole("button", { name: "Conversations", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "TEST ONLY browser microphone pipeline" }),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "A clearer picture." }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Conversations", exact: true })
    .click();
  await expect(
    page.getByRole("button", { name: "TEST ONLY browser microphone pipeline" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});
test("phone viewport navigation and no horizontal overflow (physical phone microphone NOT VERIFIED)", async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await signIn(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
  await page.screenshot({
    path: path.join(screenshotDir, "dashboard-mobile.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("button", { name: "Devices", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "Capture devices." }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Register device" }).click();
  await page.getByLabel("Device name").fill("TEST ONLY simulator");
  await page.getByLabel("Hardware model").fill("test-model");
  await page.getByLabel("This is a development simulator").check();
  await page.getByRole("button", { name: "Register securely" }).click();
  await expect(page.getByText("Save this device credential")).toBeVisible();
  await page.getByRole("button", { name: "I’ve saved it" }).click();
  await expect(
    page.getByText("SIMULATED · software controls, no connected hardware"),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBe(true);
});
