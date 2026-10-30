import { test, expect } from "@playwright/test";
import { FarmerPage } from "../pages/FarmerPage";

/**
 * Feature: Navigation between the farmer voice UI and the
 * developer / extension worker dashboard.
 */
test.describe("Feature: Navigation", () => {
  let farmer: FarmerPage;

  test.beforeEach(async ({ page }) => {
    farmer = new FarmerPage(page);
    await farmer.goto();
  });

  test("should open the developer dashboard from the header link", async ({
    page
  }) => {
    // Act
    await farmer.devDashboardLink.click();

    // Assert: dashboard rendered
    await expect(page).toHaveURL(/\/dev$/);
    await expect(
      page.getByText("KisanSahayak Developer & Extension Dashboard")
    ).toBeVisible();
    await expect(page.getByText(/Telemetry, Vector DB chunks/)).toBeVisible();

    await page.screenshot({
      path: "artifacts/developer-dashboard.png",
      fullPage: true
    });
  });

  test("should return to the farmer voice view from the dashboard", async ({
    page
  }) => {
    // Arrange
    await farmer.devDashboardLink.click();
    await expect(page).toHaveURL(/\/dev$/);

    // Act
    await page.getByRole("link", { name: /Open Farmer Voice View/ }).click();

    // Assert: back on the farmer home screen
    await expect(page).toHaveURL(/\/$/);
    await farmer.expectLoaded();
    await expect(farmer.topicTiles).toHaveCount(5);
  });

  test("should keep the chosen language when visiting the dashboard and back", async ({
    page
  }) => {
    // Act: choose English, then leave and return
    await farmer.selectLanguage("en");
    await farmer.devDashboardLink.click();
    await expect(page).toHaveURL(/\/dev$/);
    await page.getByRole("link", { name: /Open Farmer Voice View/ }).click();
    await farmer.expectLoaded();

    // Assert: preference survived the round trip
    await expect(farmer.languageButton("en")).toHaveAttribute(
      "aria-pressed",
      "true"
    );
    await expect(farmer.micStateLabel).toContainText(
      "Tap & Speak your question"
    );
  });
});
