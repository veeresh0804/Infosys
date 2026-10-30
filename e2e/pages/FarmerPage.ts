import { Locator, Page, expect } from "@playwright/test";

/**
 * Page Object for the farmer-facing voice UI (frontend/src/app/page.tsx).
 * All selectors prefer stable `data-testid` hooks over CSS classes.
 */
export class FarmerPage {
  readonly page: Page;

  // Header / chrome
  readonly appTitle: Locator;
  readonly appTagline: Locator;
  readonly devDashboardLink: Locator;
  readonly languageSelector: Locator;

  // Voice hero
  readonly micButton: Locator;
  readonly micStateLabel: Locator;

  // Feedback banners
  readonly errorBanner: Locator;
  readonly errorMessage: Locator;
  readonly warmingBanner: Locator;
  readonly autoplayBanner: Locator;

  // Answer card
  readonly answerCard: Locator;
  readonly answerText: Locator;
  readonly weatherWidget: Locator;
  readonly mandiWidget: Locator;
  readonly expandAnswerButton: Locator;

  // Topic tiles
  readonly topicTiles: Locator;
  readonly tilesHeading: Locator;

  // Text fallback form
  readonly textToggle: Locator;
  readonly textInput: Locator;
  readonly sendButton: Locator;
  readonly cancelTextInput: Locator;

  // Conversation history
  readonly chatHistory: Locator;
  readonly chatBubbles: Locator;

  constructor(page: Page) {
    this.page = page;
    this.appTitle = page.getByTestId("app-title");
    this.appTagline = page.getByTestId("app-tagline");
    this.devDashboardLink = page.getByTestId("dev-dashboard-link");
    this.languageSelector = page.getByTestId("language-selector");
    this.micButton = page.getByTestId("mic-button");
    this.micStateLabel = page.getByTestId("mic-state-label");
    this.errorBanner = page.getByTestId("error-banner");
    this.errorMessage = page.getByTestId("error-message");
    this.warmingBanner = page.getByTestId("server-warming-banner");
    this.autoplayBanner = page.getByTestId("autoplay-banner");
    this.answerCard = page.getByTestId("answer-card");
    this.answerText = page.getByTestId("answer-text");
    this.weatherWidget = page.getByTestId("weather-widget");
    this.mandiWidget = page.getByTestId("mandi-widget");
    this.expandAnswerButton = page.getByTestId("expand-answer");
    this.topicTiles = page.locator("[data-testid^='topic-tile-']");
    this.tilesHeading = page.getByTestId("tiles-heading");
    this.textToggle = page.getByTestId("text-input-toggle");
    this.textInput = page.getByTestId("text-input");
    this.sendButton = page.getByTestId("send-button");
    this.cancelTextInput = page.getByTestId("cancel-text-input");
    this.chatHistory = page.getByTestId("chat-history");
    this.chatBubbles = page.getByTestId("chat-bubble");
  }

  /** Navigate to the farmer UI and wait until the hero is interactive. */
  async goto() {
    await this.page.goto("/");
    await this.expectLoaded();
  }

  async expectLoaded() {
    await expect(this.appTitle).toBeVisible();
    await expect(this.micButton).toBeVisible();
    await expect(this.languageSelector).toBeVisible();
  }

  languageButton(code: "hi" | "kn" | "en"): Locator {
    return this.page.getByTestId(`lang-${code}`);
  }

  topicTile(
    id: "crop_care" | "pests" | "mandi" | "weather" | "schemes"
  ): Locator {
    return this.page.getByTestId(`topic-tile-${id}`);
  }

  async selectLanguage(code: "hi" | "kn" | "en") {
    await this.languageButton(code).click();
    await expect(this.languageButton(code)).toHaveAttribute("aria-pressed", "true");
  }

  /** Reveal the secondary text input and ask a typed question. */
  async askTextQuestion(question: string) {
    if (await this.textInput.isVisible().catch(() => false)) {
      await this.textInput.fill(question);
    } else {
      await this.textToggle.click();
      await this.textInput.fill(question);
    }

    const queryRequest = this.page.waitForRequest(
      (req) => req.url().includes("/api/rag/query") && req.method() === "POST",
      { timeout: 60_000 }
    );
    await this.sendButton.click();
    return queryRequest;
  }

  /** Wait for the RAG pipeline answer card to render with real text. */
  async waitForAnswer(timeout = 60_000) {
    await expect(this.answerCard).toBeVisible({ timeout });
    await expect(this.answerText).not.toBeEmpty({ timeout });
  }
}
