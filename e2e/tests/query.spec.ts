import { test, expect } from "@playwright/test";
import { FarmerPage } from "../pages/FarmerPage";

/**
 * Feature: Ask a Question (typed happy path + picture-tile shortcuts)
 * This is the product's core value: farmer asks -> grounded, labelled advice.
 */
test.describe("Feature: Ask a Question", () => {
  let farmer: FarmerPage;

  test.beforeEach(async ({ page }) => {
    farmer = new FarmerPage(page);
    await farmer.goto();
    // Deterministic assertions: read the reply in English.
    await farmer.selectLanguage("en");
  });

  test("should answer a typed question with a labelled advice card", async ({
    page
  }) => {
    test.setTimeout(150_000);

    // Act: ask through the secondary text fallback
    const request = await farmer.askTextQuestion(
      "What is today's mandi market price for tomato and paddy?"
    );
    const response = await request.response();
    expect(response, "RAG pipeline should answer the query").toBeTruthy();
    expect(response!.status()).toBe(200);

    // Assert: pipeline telemetry is honest about the engine used
    const payload = await response!.json();
    expect(payload.session_id).toBeTruthy();
    expect(payload.intent).toBe("market_prices");
    expect(payload.answer_translated.length).toBeGreaterThan(10);
    expect(payload.engine_used).toBeTruthy();

    // Assert: advice card rendered for the farmer
    await farmer.waitForAnswer();
    await expect(farmer.answerText).toContainText(/₹|price|Price/);

    // Assert: conversation history now exists
    await expect(farmer.chatHistory).toBeVisible();
    expect(await farmer.chatBubbles.count()).toBeGreaterThanOrEqual(1);

    await page.screenshot({
      path: "artifacts/typed-question-answer.png",
      fullPage: true
    });
  });

  test("should show a mandi price widget when the Market Prices tile is tapped", async ({
    page
  }) => {
    test.setTimeout(150_000);

    // Act
    const responsePromise = page.waitForResponse(
      (res) =>
        res.url().includes("/api/rag/query") && res.request().method() === "POST",
      { timeout: 90_000 }
    );
    await farmer.topicTile("mandi").click();
    const response = await responsePromise;

    // Assert: response carries live/sample APMC rows
    expect(response.status()).toBe(200);
    const payload = await response.json();
    expect(payload.sub_agent).toBe("market_prices");
    expect(payload.live_data?.mandi_prices?.length).toBeGreaterThan(0);

    // Assert: visual price card is rendered
    await expect(farmer.mandiWidget).toBeVisible({ timeout: 30_000 });
    await expect(farmer.mandiWidget).toContainText("₹");
    await expect(farmer.mandiWidget).toContainText(/per quintal/);

    await page.screenshot({
      path: "artifacts/mandi-widget.png",
      fullPage: true
    });
  });

  test("should show live weather when the Weather Forecast tile is tapped", async ({
    page
  }) => {
    test.setTimeout(150_000);

    // Act
    const responsePromise = page.waitForResponse(
      (res) =>
        res.url().includes("/api/rag/query") && res.request().method() === "POST",
      { timeout: 90_000 }
    );
    await farmer.topicTile("weather").click();
    const response = await responsePromise;

    // Assert: weather agent answered with Open-Meteo data
    expect(response.status()).toBe(200);
    const payload = await response.json();
    expect(payload.sub_agent).toBe("weather");
    expect(typeof payload.live_data?.weather?.temperature).toBe("number");

    // Assert: visual weather widget renders temperature + advisory
    await expect(farmer.weatherWidget).toBeVisible({ timeout: 30_000 });
    await expect(farmer.weatherWidget).toContainText("°C");
    await expect(farmer.weatherWidget).toContainText(/Weather Advisory/);

    await page.screenshot({
      path: "artifacts/weather-widget.png",
      fullPage: true
    });
  });

  test("should expand long answers with the Read more control", async ({
    page
  }) => {
    test.setTimeout(150_000);

    // Act: ask a broad advisory question that produces a long answer
    await farmer.askTextQuestion(
      "How to improve crop yield and manage fertilizer for paddy and wheat?"
    );
    await farmer.waitForAnswer();

    // Assert: expansion is offered only for long answers (conditional UI)
    if (await farmer.expandAnswerButton.isVisible()) {
      const shortAnswer = await farmer.answerText.innerText();
      await farmer.expandAnswerButton.click();
      const fullAnswer = await farmer.answerText.innerText();
      expect(fullAnswer.length).toBeGreaterThanOrEqual(shortAnswer.length);
      await expect(farmer.expandAnswerButton).toContainText(/Show less/);
    } else {
      // Short answer: read-more must not be offered
      await expect(farmer.answerText).toBeVisible();
    }
  });
});
