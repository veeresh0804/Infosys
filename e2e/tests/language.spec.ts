import { test, expect } from "@playwright/test";
import { FarmerPage } from "../pages/FarmerPage";
import { sessionUrl } from "../support/api";

/**
 * Feature: Multilingual UI (Hindi / Kannada / English)
 * Rural users switch language with a single thumb tap; the choice must
 * repaint the UI immediately and survive a reload.
 */
test.describe("Feature: Language Selection", () => {
  let farmer: FarmerPage;

  test.beforeEach(async ({ page }) => {
    farmer = new FarmerPage(page);
    await farmer.goto();
  });

  test("should default to Hindi on a first visit", async ({ page }) => {
    // Assert: Hindi is the pre-selected language
    await expect(farmer.languageButton("hi")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    await expect(farmer.languageButton("en")).toHaveAttribute(
      "aria-pressed",
      "false"
    );

    // Assert: mic prompt rendered in Devanagari
    await expect(farmer.micStateLabel).not.toContainText(
      "Tap & Speak your question"
    );
  });

  test("should repaint the whole UI when English is selected", async ({
    page
  }) => {
    // Act
    await farmer.selectLanguage("en");

    // Assert: selector state
    await expect(farmer.languageButton("en")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    await expect(farmer.languageButton("hi")).toHaveAttribute(
      "aria-pressed",
      "false"
    );

    // Assert: voice hub + tiles copy switched
    await expect(farmer.micStateLabel).toContainText(
      "Tap & Speak your question"
    );
    await expect(farmer.tilesHeading).toContainText(
      "Or choose a farming topic:"
    );
    await expect(farmer.topicTile("mandi")).toHaveAttribute(
      "aria-label",
      "Market Prices"
    );

    // Assert: preference persisted for the next session
    expect(
      await page.evaluate(() => localStorage.getItem("kisan_farmer_lang"))
    ).toBe("en");
  });

  test("should render Kannada labels and keep the choice after reload", async ({
    page
  }) => {
    // Act
    await farmer.selectLanguage("kn");

    // Assert: native Kannada script is visible on the tile
    await expect(farmer.topicTile("weather")).toHaveAttribute(
      "aria-label",
      "ಹವಾಮಾನ"
    );
    await expect(farmer.topicTile("schemes")).toHaveAttribute(
      "aria-label",
      "ಸರ್ಕಾರಿ ಯೋಜನೆಗಳು"
    );

    // Act: reload the app
    await page.reload();
    await farmer.expectLoaded();

    // Assert: selection restored from localStorage
    await expect(farmer.languageButton("kn")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    await expect(farmer.topicTile("weather")).toHaveAttribute(
      "aria-label",
      "ಹವಾಮಾನ"
    );
  });

  test("should sync the preferred language to the backend session", async ({
    page
  }) => {
    // Act: switch to Kannada (fire-and-forget PATCH from the UI)
    const patchPromise = page.waitForResponse(
      (res) =>
        res.url().includes("/api/sessions/") && res.request().method() === "PATCH"
    );
    await farmer.selectLanguage("kn");
    const patch = await patchPromise;

    // Assert: backend acknowledged the preference write
    expect(patch.status()).toBe(200);
    const body = await patch.json();
    expect(body.preferred_language).toBe("kn");

    const sessionId = await page.evaluate(() =>
      localStorage.getItem("kisan_session_id")
    );
    const res = await page.request.get(sessionUrl(sessionId!));
    expect(res.ok()).toBeTruthy();
    const session = await res.json();
    expect(session.preferred_language).toBe("kn");
  });
});
