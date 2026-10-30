import { test, expect } from "@playwright/test";
import { FarmerPage } from "../pages/FarmerPage";
import { sessionUrl } from "../support/api";

/**
 * Feature: Landing & Core Controls
 * Critical first impression for a low-literacy voice-first user.
 */
test.describe("Feature: Landing & Core Controls", () => {
  let farmer: FarmerPage;

  test.beforeEach(async ({ page }) => {
    farmer = new FarmerPage(page);
    await farmer.goto();
  });

  test.afterEach(async ({ page }, testInfo) => {
    if (testInfo.status !== "passed") {
      await page.screenshot({
        path: `artifacts/${testInfo.title.replace(/[^\w]+/g, "-").toLowerCase()}.png`,
        fullPage: true
      });
    }
  });

  test("should render brand, language selector, mic hub and all five topic tiles", async ({
    page
  }) => {
    // Arrange + Act already done in beforeEach

    // Assert: header (title is localised, so only require a non-empty brand)
    await expect(farmer.appTitle).toContainText("🌱");
    await expect(farmer.appTitle).not.toBeEmpty();
    await expect(farmer.appTagline).toBeVisible();

    // Assert: three thumb-sized language buttons (हिन्दी / ಕನ್ನಡ / English)
    const langHi = farmer.languageButton("hi");
    const langKn = farmer.languageButton("kn");
    const langEn = farmer.languageButton("en");
    await expect(langHi).toBeVisible();
    await expect(langKn).toBeVisible();
    await expect(langEn).toBeVisible();
    await expect(langHi).toHaveText(/हिन्दी/);

    // Assert: central voice hub
    await expect(farmer.micButton).toBeVisible();
    await expect(farmer.micStateLabel).toHaveText(/दबाएं|ಒತ್ತಿ|Tap & Speak/);

    // Assert: all five agriculture topics
    await expect(farmer.topicTiles).toHaveCount(5);
    for (const id of ["crop_care", "pests", "mandi", "weather", "schemes"]) {
      await expect(farmer.topicTile(id as any)).toBeVisible();
    }

    // Assert: secondary text fallback is reachable
    await expect(farmer.textToggle).toBeVisible();

    // Artifact: baseline landing screenshot
    await page.screenshot({ path: "artifacts/landing-page.png", fullPage: true });
  });

  test("should create a unique farmer session id on first visit", async ({
    page
  }) => {
    // Arrange: fresh storage (new context per test)

    // Act: page mount effect generates the session
    const sessionId = (await page.evaluate(() =>
      localStorage.getItem("kisan_session_id")
    )) as string;

    // Assert: session exists and is not the hardcoded default
    expect(sessionId).toBeTruthy();
    expect(sessionId).toMatch(/^farmer-/);
    expect(sessionId).not.toBe("default-session");

    // Assert: backend session record exists for this id and picked up the
    // language preference the UI PATCHes on mount (default is "en").
    const res = await page.request.get(sessionUrl(sessionId));
    expect(res.ok()).toBeTruthy();
    const session = await res.json();
    expect(session.session_id).toBe(sessionId);

    await expect
      .poll(async () => {
        const r = await page.request.get(sessionUrl(sessionId));
        const data = await r.json();
        return data.preferred_language;
      }, { timeout: 20_000 })
      .toBe("hi");
  });

  test("should disable the Ask button until a question is typed", async ({
    page
  }) => {
    // Arrange
    await farmer.textToggle.click();

    // Assert: empty input keeps submit disabled
    await expect(farmer.sendButton).toBeDisabled();

    // Act
    await farmer.textInput.fill(" ");

    // Assert: whitespace-only stays disabled (trim guard)
    await expect(farmer.sendButton).toBeDisabled();

    await farmer.textInput.fill("What is the price of tomato?");

    // Assert: real content enables submit
    await expect(farmer.sendButton).toBeEnabled();
  });
});
