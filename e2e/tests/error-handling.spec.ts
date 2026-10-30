import { test, expect } from "@playwright/test";
import { FarmerPage } from "../pages/FarmerPage";

/**
 * Feature: Failure Handling
 * The assistant must never look "broken" - every failure becomes a readable,
 * announced (role=alert) message instead of a blank screen.
 */
test.describe("Feature: Failure Handling", () => {
  let farmer: FarmerPage;

  test.beforeEach(async ({ page }) => {
    farmer = new FarmerPage(page);
    await farmer.goto();
    await farmer.selectLanguage("en");
  });

  test.afterEach(async ({ page }, testInfo) => {
    if (testInfo.status !== "passed") {
      await page.screenshot({
        path: `artifacts/${testInfo.title.replace(/[^\w]+/g, "-").toLowerCase()}.png`,
        fullPage: true
      });
    }
  });

  test("should surface a friendly error when the backend is unreachable", async ({
    page
  }) => {
    // Arrange: simulate total network loss on the query pipeline
    await page.route("**/api/rag/query", (route) => route.abort("failed"));

    // Act
    await farmer.askTextQuestion("What is the price of tomato?");

    // Assert: the user gets an announced error instead of a silent hang
    await expect(farmer.errorBanner).toBeVisible({ timeout: 30_000 });
    await expect(farmer.errorMessage).not.toBeEmpty();

    // Assert: mic hub returns to its resting state
    await expect(farmer.micStateLabel).toContainText(/Tap & Speak/);

    await page.screenshot({
      path: "artifacts/network-failure-banner.png",
      fullPage: true
    });
  });

  test("should show the backend's failure reason on HTTP 500", async ({
    page
  }) => {
    // Arrange: pipeline crashes server-side
    await page.route("**/api/rag/query", (route) =>
      route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({ detail: "Pipeline temporarily unavailable" })
      })
    );

    // Act
    await farmer.askTextQuestion("Any advice for leaf curl virus?");

    // Assert: honest, specific message is surfaced
    await expect(farmer.errorBanner).toBeVisible({ timeout: 20_000 });
    await expect(farmer.errorMessage).toContainText(
      "Pipeline temporarily unavailable"
    );
  });

  test("should explain microphone denial when permission is not granted", async ({
    page
  }) => {
    // Arrange: no microphone permission granted to this context
    await page.context().clearPermissions();

    // Act: tap the big mic button
    await farmer.micButton.click();

    // Assert: permission guidance is shown and announced
    await expect(farmer.errorBanner).toBeVisible({ timeout: 20_000 });
    await expect(farmer.errorMessage).toContainText(
      "Microphone permission is required"
    );

    // Assert: no fake transcript was added to the conversation
    await expect(farmer.chatHistory).toHaveCount(0);

    await page.screenshot({
      path: "artifacts/mic-permission-error.png",
      fullPage: true
    });
  });

  test("should recover and answer the next question after a failure", async ({
    page
  }) => {
    // Arrange: fail only the first attempt
    let attempt = 0;
    await page.route("**/api/rag/query", async (route) => {
      attempt += 1;
      if (attempt === 1) {
        await route.abort("failed");
      } else {
        await route.continue();
      }
    });

    // Act 1: failing question
    await farmer.askTextQuestion("What is the price of tomato?");
    await expect(farmer.errorBanner).toBeVisible({ timeout: 30_000 });

    // Act 2: same form, healthy backend
    await farmer.textInput.fill("What is the weather forecast today?");
    await farmer.sendButton.click();

    // Assert: pipeline recovers and the advice card renders
    await farmer.waitForAnswer(90_000);

    // Assert: previous failure is no longer the active banner state
    await expect(farmer.answerCard).toBeVisible();
  });
});
