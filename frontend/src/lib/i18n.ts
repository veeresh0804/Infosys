"use client";

import en from "../locales/en.json";
import hi from "../locales/hi.json";
import kn from "../locales/kn.json";

export type LanguageCode = "hi" | "kn" | "en";

export const translations: Record<LanguageCode, Record<string, string>> = {
  hi,
  kn,
  en
};

export function getTranslation(lang: LanguageCode, key: string): string {
  const dict = translations[lang] || translations.hi;
  return dict[key] || translations.en[key] || key;
}

export const LANGUAGE_OPTIONS: { code: LanguageCode; nativeLabel: string; englishLabel: string }[] = [
  { code: "hi", nativeLabel: "हिन्दी", englishLabel: "Hindi" },
  { code: "kn", nativeLabel: "ಕನ್ನಡ", englishLabel: "Kannada" },
  { code: "en", nativeLabel: "English", englishLabel: "English" }
];
