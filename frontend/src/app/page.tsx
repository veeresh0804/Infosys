"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  LanguageCode,
  LANGUAGE_OPTIONS,
  getTranslation
} from "../lib/i18n";
import {
  MicIcon,
  StopIcon,
  SpeakerIcon,
  CropIcon,
  PestIcon,
  PriceIcon,
  WeatherIcon,
  SchemeIcon,
  AlertIcon
} from "../components/Icons";
import { api, QueryResponse } from "../lib/api";

type MicState = "idle" | "listening" | "thinking" | "speaking";

interface FarmerMessage {
  id: string;
  sender: "farmer" | "assistant";
  text: string;
  shortText?: string;
  fullText?: string;
  isExpanded?: boolean;
  audioBase64?: string;
  liveData?: any;
  subAgent?: string;
}

export default function FarmerPage() {
  const [lang, setLang] = useState<LanguageCode>("hi");
  const [micState, setMicState] = useState<MicState>("idle");
  const [messages, setMessages] = useState<FarmerMessage[]>([]);
  const [currentResponse, setCurrentResponse] = useState<QueryResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [manualText, setManualText] = useState("");
  const [showTextInput, setShowTextInput] = useState(false);
  const [autoplayBlocked, setAutoplayBlocked] = useState(false);

  // Audio refs
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const sessionIdRef = useRef("farmer-session-main");

  // Load language preference from localStorage on mount
  useEffect(() => {
    const savedLang = localStorage.getItem("kisan_farmer_lang") as LanguageCode;
    if (savedLang && (savedLang === "hi" || savedLang === "kn" || savedLang === "en")) {
      setLang(savedLang);
    }
  }, []);

  const changeLanguage = (newLang: LanguageCode) => {
    setLang(newLang);
    localStorage.setItem("kisan_farmer_lang", newLang);
    stopCurrentAudio();
    // Update session preference on backend silently
    api.updateSession(sessionIdRef.current, { preferred_language: newLang }).catch(() => {});
  };

  const t = (key: string) => getTranslation(lang, key);

  // Stop currently playing audio
  const stopCurrentAudio = () => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause();
      currentAudioRef.current.currentTime = 0;
      currentAudioRef.current = null;
    }
    if (micState === "speaking") {
      setMicState("idle");
    }
  };

  // Play audio from base64 string
  const playAudioBase64 = async (b64: string): Promise<boolean> => {
    stopCurrentAudio();
    try {
      const audio = new Audio("data:audio/wav;base64," + b64);
      currentAudioRef.current = audio;
      setMicState("speaking");

      audio.onended = () => {
        setMicState("idle");
        currentAudioRef.current = null;
      };
      audio.onerror = () => {
        setMicState("idle");
        currentAudioRef.current = null;
      };

      await audio.play();
      setAutoplayBlocked(false);
      return true;
    } catch (err: any) {
      console.warn("Autoplay blocked or audio playback failed:", err);
      setMicState("idle");
      setAutoplayBlocked(true);
      return false;
    }
  };

  // Play static tile audio
  const playTileAudio = (tileId: string) => {
    stopCurrentAudio();
    const audioPath = `/audio/tiles/${tileId}_${lang}.wav`;
    const audio = new Audio(audioPath);
    currentAudioRef.current = audio;

    audio.onended = () => {
      currentAudioRef.current = null;
    };
    audio.onerror = () => {
      console.warn(`Tile audio file missing: ${audioPath}`);
      currentAudioRef.current = null;
      // Speech synthesis fallback if static file missing
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        const textMap: Record<string, Record<LanguageCode, string>> = {
          crop_care: { en: "Crop Care", hi: "फसल देखभाल", kn: "ಬೆಳೆ ನಿರ್ವಹಣೆ" },
          pests: { en: "Pests and Diseases", hi: "कीट और रोग", kn: "ಕೀಟ ಮತ್ತು ರೋಗ" },
          mandi: { en: "Market Prices", hi: "मंडी भाव", kn: "ಮಾರುಕಟ್ಟೆ ದರ" },
          weather: { en: "Weather Forecast", hi: "मौसम", kn: "ಹವಾಮಾನ" },
          schemes: { en: "Government Schemes", hi: "सरकारी योजनाएं", kn: "ಸರ್ಕಾರಿ ಯೋಜನೆಗಳು" }
        };
        const u = new SpeechSynthesisUtterance(textMap[tileId]?.[lang] || tileId);
        u.lang = lang === "hi" ? "hi-IN" : lang === "kn" ? "kn-IN" : "en-IN";
        window.speechSynthesis.speak(u);
      }
    };

    audio.play().catch(() => {});
  };

  // Speak friendly error message aloud
  const speakErrorMessage = async (errText: string) => {
    try {
      const b64 = await api.synthesizeSpeech(errText, lang);
      if (b64) await playAudioBase64(b64);
    } catch {
      if (typeof window !== "undefined" && "speechSynthesis" in window) {
        const u = new SpeechSynthesisUtterance(errText);
        u.lang = lang === "hi" ? "hi-IN" : lang === "kn" ? "kn-IN" : "en-IN";
        window.speechSynthesis.speak(u);
      }
    }
  };

  // Start microphone recording
  const startRecording = async () => {
    stopCurrentAudio();
    setErrorMessage(null);
    setAutoplayBlocked(false);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/wav" });
        stream.getTracks().forEach((track) => track.stop());

        const reader = new FileReader();
        reader.onloadend = async () => {
          const base64Audio = (reader.result as string).split(",")[1];
          await processQuery("", base64Audio);
        };
        reader.readAsDataURL(audioBlob);
      };

      mediaRecorder.start();
      setMicState("listening");
    } catch (err: any) {
      console.error("Mic access error:", err);
      setMicState("idle");
      const deniedMsg = t("err_mic_denied");
      setErrorMessage(deniedMsg);
      speakErrorMessage(deniedMsg);
    }
  };

  // Stop recording and trigger processing
  const stopRecording = () => {
    if (mediaRecorderRef.current && micState === "listening") {
      mediaRecorderRef.current.stop();
      setMicState("thinking");
    }
  };

  // Process query via backend pipeline
  const processQuery = async (queryText?: string, audioBase64?: string) => {
    setMicState("thinking");
    setErrorMessage(null);

    const userMessageId = "msg-" + Date.now();
    const userMsg: FarmerMessage = {
      id: userMessageId,
      sender: "farmer",
      text: queryText || (lang === "hi" ? "🎤 [आपकी आवाज़]" : lang === "kn" ? "🎤 [ನಿಮ್ಮ ಧ್ವನಿ]" : "🎤 [Voice Question]")
    };
    setMessages((prev) => [...prev, userMsg]);

    try {
      const res = await api.queryPipeline({
        sessionId: sessionIdRef.current,
        text: queryText || undefined,
        language: lang,
        audioBase64
      });

      setCurrentResponse(res);

      // Prefer short_answer_translated for concise voice & screen presentation
      const spokenText = res.short_answer_translated || res.answer_translated;
      const fullText = res.answer_translated;
      const shortText = res.short_answer_translated || fullText.slice(0, 180);

      const assistantMsg: FarmerMessage = {
        id: "resp-" + Date.now(),
        sender: "assistant",
        text: shortText,
        shortText,
        fullText,
        isExpanded: false,
        liveData: res.live_data,
        subAgent: res.sub_agent
      };

      setMessages((prev) => [...prev, assistantMsg]);

      // Automatically synthesize & play answer aloud via Sarvam TTS
      try {
        const audioB64 = await api.synthesizeSpeech(spokenText, lang);
        assistantMsg.audioBase64 = audioB64;
        if (audioB64) {
          const played = await playAudioBase64(audioB64);
          if (!played) {
            setAutoplayBlocked(true);
          }
        } else {
          setMicState("idle");
        }
      } catch (audioErr) {
        console.warn("TTS generation error:", audioErr);
        setMicState("idle");
      }
    } catch (err: any) {
      console.error("Query pipeline failed:", err);
      setMicState("idle");
      const netErrMsg = t("err_network");
      setErrorMessage(netErrMsg);
      speakErrorMessage(netErrMsg);
      setMessages((prev) => [
        ...prev,
        {
          id: "err-" + Date.now(),
          sender: "assistant",
          text: netErrMsg
        }
      ]);
    }
  };

  // Picture tile definitions with pre-recorded audio triggers
  const TOPIC_TILES = [
    {
      id: "crop_care",
      label: t("topic_crop_care"),
      icon: <CropIcon size={36} />,
      prompt: t("prompt_crop_care")
    },
    {
      id: "pests",
      label: t("topic_pests"),
      icon: <PestIcon size={36} />,
      prompt: t("prompt_pests")
    },
    {
      id: "mandi",
      label: t("topic_mandi"),
      icon: <PriceIcon size={36} />,
      prompt: t("prompt_mandi")
    },
    {
      id: "weather",
      label: t("topic_weather"),
      icon: <WeatherIcon size={36} />,
      prompt: t("prompt_weather")
    },
    {
      id: "schemes",
      label: t("topic_schemes"),
      icon: <SchemeIcon size={36} />,
      prompt: t("prompt_schemes")
    }
  ];

  const handleTileClick = (tileId: string, promptText: string) => {
    playTileAudio(tileId);
    processQuery(promptText);
  };

  const toggleExpand = (msgId: string) => {
    setMessages((prev) =>
      prev.map((m) =>
        m.id === msgId ? { ...m, isExpanded: !m.isExpanded } : m
      )
    );
  };

  const lastAssistantMessage = [...messages].reverse().find((m) => m.sender === "assistant");

  return (
    <div className="farmer-page-root">
      {/* Top Banner & Language Selector */}
      <header className="farmer-top-nav">
        <div className="farmer-brand-block">
          <h1 className="farmer-app-name">🌱 {t("app_title")}</h1>
          <p className="farmer-app-tagline">{t("app_subtitle")}</p>
        </div>

        <Link href="/dev" className="farmer-dev-link" title="Open Developer Dashboard">
          {t("dev_link")}
        </Link>
      </header>

      {/* Language Buttons: Large, Thumb-friendly, In Native Script */}
      <section className="farmer-lang-selector-strip" aria-label="Language Selector">
        {LANGUAGE_OPTIONS.map((opt) => (
          <button
            key={opt.code}
            type="button"
            onClick={() => changeLanguage(opt.code)}
            className={`farmer-lang-button ${lang === opt.code ? "selected" : ""}`}
            aria-pressed={lang === opt.code}
          >
            <span className="lang-native-text">{opt.nativeLabel}</span>
            <span className="lang-sub-label">{opt.englishLabel}</span>
          </button>
        ))}
      </section>

      {/* Friendly Error Banner with Voice Read-out */}
      {errorMessage && (
        <aside className="farmer-error-banner" role="alert">
          <AlertIcon size={32} className="error-icon" />
          <div className="error-text-wrap">
            <p className="error-message-text">{errorMessage}</p>
            <button
              type="button"
              onClick={() => speakErrorMessage(errorMessage)}
              className="farmer-small-audio-btn"
            >
              🔊 {t("btn_listen")}
            </button>
          </div>
        </aside>
      )}

      {/* Autoplay blocked prompt */}
      {autoplayBlocked && (
        <aside className="farmer-notice-banner" role="status">
          <SpeakerIcon size={28} />
          <span>Tap to hear the advice aloud:</span>
          <button
            type="button"
            onClick={() => {
              if (lastAssistantMessage?.audioBase64) {
                playAudioBase64(lastAssistantMessage.audioBase64);
              } else if (lastAssistantMessage?.text) {
                api.synthesizeSpeech(lastAssistantMessage.text, lang).then(playAudioBase64);
              }
            }}
            className="farmer-btn-highlight"
          >
            ▶ {t("btn_listen")}
          </button>
        </aside>
      )}

      {/* Central Large Microphone Voice Interaction Hub */}
      <main className="farmer-voice-hero">
        <div className="mic-interactive-wrapper">
          {micState === "idle" && (
            <button
              type="button"
              onClick={startRecording}
              className="farmer-mic-btn idle"
              aria-label={t("mic_idle")}
            >
              <MicIcon size={56} className="mic-svg" />
            </button>
          )}

          {micState === "listening" && (
            <button
              type="button"
              onClick={stopRecording}
              className="farmer-mic-btn listening"
              aria-label={t("mic_listening")}
            >
              <div className="listening-pulse-ring" />
              <StopIcon size={52} className="stop-svg" />
            </button>
          )}

          {micState === "thinking" && (
            <div className="farmer-mic-btn thinking" aria-live="polite">
              <div className="thinking-sprout">🌱</div>
            </div>
          )}

          {micState === "speaking" && (
            <button
              type="button"
              onClick={stopCurrentAudio}
              className="farmer-mic-btn speaking"
              aria-label={t("btn_stop")}
            >
              <div className="speaking-wave-ring" />
              <SpeakerIcon size={52} className="speaker-svg" />
            </button>
          )}

          {/* Current State Label (in selected native language) */}
          <div className="mic-state-label-box">
            {micState === "idle" && <p className="mic-state-text idle">{t("mic_idle")}</p>}
            {micState === "listening" && <p className="mic-state-text listening">{t("mic_listening")}</p>}
            {micState === "thinking" && <p className="mic-state-text thinking">{t("mic_thinking")}</p>}
            {micState === "speaking" && (
              <div className="speaking-control-row">
                <span className="mic-state-text speaking">{t("mic_speaking")}</span>
                <button
                  type="button"
                  onClick={stopCurrentAudio}
                  className="farmer-btn-stop"
                >
                  ⏹ {t("btn_stop")}
                </button>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* Visual Answer Card: Formatted for Low Literacy (Weather / Mandi / Advisory) */}
      {lastAssistantMessage && (
        <section className="farmer-answer-card" aria-live="polite">
          {/* Weather Visual Widget */}
          {lastAssistantMessage.liveData?.weather && (
            <div className="farmer-visual-weather-box">
              <div className="weather-top-row">
                <div className="weather-icon-symbol">🌦️</div>
                <div className="weather-main-digits">
                  <span className="weather-temp-num">
                    {Math.round(lastAssistantMessage.liveData.weather.temperature)}°C
                  </span>
                  <span className="weather-location-label">
                    {lastAssistantMessage.liveData.weather.location}
                  </span>
                </div>
              </div>
              <div className="weather-advisory-pill">
                <strong>🌾 {t("weather_badge")}:</strong>{" "}
                {lastAssistantMessage.liveData.weather.advisory}
              </div>
            </div>
          )}

          {/* Market Price Visual Widget */}
          {lastAssistantMessage.liveData?.mandi_prices && lastAssistantMessage.liveData.mandi_prices.length > 0 && (
            <div className="farmer-visual-mandi-box">
              {(() => {
                const topMandi = lastAssistantMessage.liveData.mandi_prices[0];
                return (
                  <div>
                    <div className="mandi-crop-header">
                      <span className="mandi-crop-name">🍅 {topMandi.commodity}</span>
                      <span className="mandi-market-name">{topMandi.market} ({topMandi.state})</span>
                    </div>
                    <div className="mandi-price-display">
                      <span className="mandi-price-currency">₹</span>
                      <span className="mandi-price-figure">{topMandi.modal_price.toLocaleString("en-IN")}</span>
                      <span className="mandi-price-unit">{t("price_per_qtl")}</span>
                    </div>
                    <div className="mandi-min-max-row">
                      <span>{t("min_max_label")}: ₹{topMandi.min_price} - ₹{topMandi.max_price}</span>
                    </div>
                  </div>
                );
              })()}
            </div>
          )}

          {/* Spoken Answer Text */}
          <div className="farmer-answer-body">
            <p className="farmer-answer-text">
              {lastAssistantMessage.isExpanded
                ? lastAssistantMessage.fullText || lastAssistantMessage.text
                : lastAssistantMessage.shortText || lastAssistantMessage.text}
            </p>

            {lastAssistantMessage.fullText && lastAssistantMessage.fullText.length > 200 && (
              <button
                type="button"
                onClick={() => toggleExpand(lastAssistantMessage.id)}
                className="farmer-btn-expand"
              >
                {lastAssistantMessage.isExpanded ? t("btn_show_less") : `▼ ${t("btn_read_more")}`}
              </button>
            )}
          </div>

          {/* Audio Controls: Replay / Stop */}
          <div className="farmer-audio-actions">
            <button
              type="button"
              onClick={async () => {
                if (lastAssistantMessage.audioBase64) {
                  playAudioBase64(lastAssistantMessage.audioBase64);
                } else {
                  const b64 = await api.synthesizeSpeech(lastAssistantMessage.shortText || lastAssistantMessage.text, lang);
                  lastAssistantMessage.audioBase64 = b64;
                  if (b64) playAudioBase64(b64);
                }
              }}
              className="farmer-audio-btn-large"
            >
              <SpeakerIcon size={24} /> {t("btn_replay")}
            </button>

            {micState === "speaking" && (
              <button
                type="button"
                onClick={stopCurrentAudio}
                className="farmer-audio-btn-stop"
              >
                <StopIcon size={20} /> {t("btn_stop")}
              </button>
            )}
          </div>
        </section>
      )}

      {/* Picture Tiles for Common Agricultural Topics */}
      <section className="farmer-tiles-section" aria-label="Topic Selection">
        <h2 className="tiles-section-heading">{t("quick_topics")}</h2>
        <div className="farmer-tiles-grid">
          {TOPIC_TILES.map((tile) => (
            <button
              key={tile.id}
              type="button"
              onClick={() => handleTileClick(tile.id, tile.prompt)}
              className="farmer-topic-tile"
              aria-label={tile.label}
            >
              <div className="tile-icon-bubble">{tile.icon}</div>
              <span className="tile-caption">{tile.label}</span>
            </button>
          ))}
        </div>
      </section>

      {/* Optional Conversation History (Collapsible Fallback for Text Users) */}
      {messages.length > 1 && (
        <section className="farmer-history-section">
          <h3 className="farmer-history-heading">📜 {t("chat_history_title")}</h3>
          <div className="farmer-history-list">
            {messages.slice(1).map((msg) => (
              <div key={msg.id} className={`farmer-chat-bubble ${msg.sender}`}>
                <p className="bubble-text">{msg.shortText || msg.text}</p>
                {msg.sender === "assistant" && (
                  <button
                    type="button"
                    onClick={async () => {
                      if (msg.audioBase64) {
                        playAudioBase64(msg.audioBase64);
                      } else {
                        const b64 = await api.synthesizeSpeech(msg.shortText || msg.text, lang);
                        msg.audioBase64 = b64;
                        if (b64) playAudioBase64(b64);
                      }
                    }}
                    className="bubble-listen-btn"
                  >
                    🔊 {t("btn_listen")}
                  </button>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Optional Text Input Toggle (Secondary Fallback) */}
      <footer className="farmer-footer-fallback">
        {!showTextInput ? (
          <button
            type="button"
            onClick={() => setShowTextInput(true)}
            className="farmer-toggle-text-btn"
          >
            ⌨️ {t("text_input_placeholder")}
          </button>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (manualText.trim()) {
                processQuery(manualText);
                setManualText("");
              }
            }}
            className="farmer-text-form"
          >
            <input
              type="text"
              value={manualText}
              onChange={(e) => setManualText(e.target.value)}
              placeholder={t("text_input_placeholder")}
              className="farmer-input-field"
            />
            <button type="submit" disabled={!manualText.trim()} className="farmer-send-btn">
              {t("send_button")}
            </button>
            <button
              type="button"
              onClick={() => setShowTextInput(false)}
              className="farmer-cancel-text-btn"
            >
              ✕
            </button>
          </form>
        )}
      </footer>
    </div>
  );
}
