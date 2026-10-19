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
  const [serverWarmingUp, setServerWarmingUp] = useState(false);

  // Audio refs
  const currentAudioRef = useRef<HTMLAudioElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const sessionIdRef = useRef<string>("farmer-session-temp");

  // Load random session ID and language preference on mount, sync with backend (Task 3, Task 6)
  useEffect(() => {
    // Generate or restore random browser session ID (Task 6: never hardcode default-session)
    let sid = localStorage.getItem("kisan_session_id");
    if (!sid) {
      sid = "farmer-" + Math.random().toString(36).substring(2, 9) + "-" + Date.now().toString(36);
      localStorage.setItem("kisan_session_id", sid);
    }
    sessionIdRef.current = sid;

    const savedLang = localStorage.getItem("kisan_farmer_lang") as LanguageCode;
    const initialLang = (savedLang && (savedLang === "hi" || savedLang === "kn" || savedLang === "en")) ? savedLang : "hi";
    if (savedLang) {
      setLang(savedLang);
    }

    // Sync saved language to backend session immediately on load (Task 3)
    api.updateSession(sid, { preferred_language: initialLang }).catch(() => { });

    // Ping /api/health to warm up sleeping free-tier host (e.g. Render 512MB web service)
    const timer = setTimeout(() => setServerWarmingUp(true), 1500);
    api.checkHealth()
      .then(() => {
        clearTimeout(timer);
        setServerWarmingUp(false);
      })
      .catch(() => {
        clearTimeout(timer);
        setServerWarmingUp(false);
      });
  }, []);

  const speakWithBrowser = (text: string, language: LanguageCode) => {
    if (typeof window === "undefined" || !("speechSynthesis" in window)) {
      setMicState("idle");
      return;
    }
    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      const bcp47 = language === "hi" ? "hi-IN" : language === "kn" ? "kn-IN" : "en-IN";
      utterance.lang = bcp47;

      const voices = window.speechSynthesis.getVoices();
      const match = voices.find(v => v.lang.startsWith(language) || v.lang.replace("_", "-") === bcp47);
      if (match) {
        utterance.voice = match;
      } else if (language === "kn") {
        setErrorMessage("ಕನ್ನಡ ಧ್ವನಿ ಈ ಬ್ರೌಸರ್‌ನಲ್ಲಿ ಲಭ್ಯವಿಲ್ಲ. ಪಠ್ಯವನ್ನು ಪರದೆಯ ಮೇಲೆ ಓದಿ. (Kannada voice not installed on device browser)");
      }

      utterance.onstart = () => setMicState("speaking");
      utterance.onend = () => setMicState("idle");
      utterance.onerror = () => setMicState("idle");
      window.speechSynthesis.speak(utterance);
    } catch (e) {
      setMicState("idle");
    }
  };

  const changeLanguage = (newLang: LanguageCode) => {
    setLang(newLang);
    localStorage.setItem("kisan_farmer_lang", newLang);
    stopCurrentAudio();
    // Update session preference on backend silently
    api.updateSession(sessionIdRef.current, { preferred_language: newLang }).catch(() => { });
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

    audio.play().catch(() => { });
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

  function getSupportedAudioMime(): { mime: string; ext: string } {
    if (typeof window === "undefined" || typeof MediaRecorder === "undefined") {
      return { mime: "audio/webm", ext: "webm" };
    }
    const candidateFormats = [
      { mime: "audio/webm;codecs=opus", ext: "webm" },
      { mime: "audio/webm", ext: "webm" },
      { mime: "audio/ogg;codecs=opus", ext: "ogg" },
      { mime: "audio/mp4", ext: "mp4" },
      { mime: "audio/wav", ext: "wav" }
    ];
    for (const fmt of candidateFormats) {
      if (MediaRecorder.isTypeSupported(fmt.mime)) {
        return fmt;
      }
    }
    return { mime: "audio/webm", ext: "webm" };
  }

  // Start microphone recording with truthful browser-supported MIME format (Task 2)
  const startRecording = async () => {
    stopCurrentAudio();
    setErrorMessage(null);
    setAutoplayBlocked(false);

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const format = getSupportedAudioMime();

      const mediaRecorder = new MediaRecorder(stream, { mimeType: format.mime });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: format.mime });
        stream.getTracks().forEach((track) => track.stop());

        const reader = new FileReader();
        reader.onloadend = async () => {
          const base64Audio = (reader.result as string).split(",")[1];
          await processQuery("", base64Audio, format.mime, `voice_query.${format.ext}`);
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

  // Process query via backend pipeline (Task 1: never invent transcripts, speak error on STT failure)
  const processQuery = async (
    queryText?: string,
    audioBase64?: string,
    audioMime?: string,
    audioFilename?: string
  ) => {
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
        audioBase64,
        audioMime,
        audioFilename
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

      // Automatically synthesize & play answer aloud via Sarvam TTS or browser Web Speech fallback
      try {
        const audioB64 = await api.synthesizeSpeech(spokenText, lang);
        assistantMsg.audioBase64 = audioB64;
        if (audioB64 && audioB64.length > 200) {
          const played = await playAudioBase64(audioB64);
          if (!played) {
            setAutoplayBlocked(true);
          }
        } else {
          // Fallback to browser client-side Web Speech synthesis
          speakWithBrowser(spokenText, lang);
        }
      } catch (audioErr) {
        console.warn("TTS generation error, using browser speech synthesis fallback:", audioErr);
        speakWithBrowser(spokenText, lang);
      }
    } catch (err: any) {
      console.error("Query pipeline failed:", err);
      setMicState("idle");

      // Task 1: on STT unavailable error, show and speak browser speech message asking farmer to retry or type
      const isSttError =
        err?.status === 422 ||
        err?.status === 503 ||
        err?.data?.error === "stt_unavailable" ||
        (err?.message && err.message.toLowerCase().includes("stt"));

      const customMsg = isSttError
        ? (lang === "hi"
            ? "आपकी आवाज़ स्पष्ट नहीं सुनाई दी। कृपया दोबारा बोलें या लिखकर पूछें।"
            : lang === "kn"
            ? "ನಿಮ್ಮ ಧ್ವನಿ ಸ್ಪಷ್ಟವಾಗಿ ಕೇಳಿಸಲಿಲ್ಲ. ದಯವಿಟ್ಟು ಮತ್ತೆ ಮಾತನಾಡಿ ಅಥವಾ ಟೈಪ್ ಮಾಡಿ."
            : "Voice input could not be transcribed. Please try speaking again or type your question.")
        : (err?.message || t("err_network"));

      setErrorMessage(customMsg);
      speakWithBrowser(customMsg, lang);
      setMessages((prev) => [
        ...prev,
        {
          id: "err-" + Date.now(),
          sender: "assistant",
          text: customMsg
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

      {/* Free Tier Server Warm-Up Banner */}
      {serverWarmingUp && (
        <aside style={{
          background: "rgba(245, 158, 11, 0.12)",
          border: "1px solid #f59e0b",
          color: "#b45309",
          padding: "10px 16px",
          borderRadius: "8px",
          fontSize: "14px",
          textAlign: "center",
          margin: "8px auto 16px auto",
          maxWidth: "600px",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          gap: "8px"
        }} role="status">
          <span>🌱</span>
          <span>
            {lang === "kn"
              ? "ಉಚಿತ ಸರ್ವರ್ ಸಕ್ರಿಯಗೊಳ್ಳುತ್ತಿದೆ (ಮೊದಲ ವಿನಂತಿಗೆ ಕೆಲವು ಸೆಕೆಂಡುಗಳು ಬೇಕಾಗಬಹುದು)..."
              : lang === "hi"
                ? "मुफ्त सर्वर चालू हो रहा है (पहली प्रतिक्रिया में कुछ सेकंड लग सकते हैं)..."
                : "Waking up free cloud server (first request may take a few seconds)..."}
          </span>
        </aside>
      )}

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
            {/* Task 9: Notice for answers based on unverified or sample knowledge base records */}
            {currentResponse?.has_unverified_sources && (
              <div
                className="farmer-unverified-warning"
                style={{
                  backgroundColor: "#fff3cd",
                  border: "1px solid #ffeeba",
                  color: "#856404",
                  padding: "10px 14px",
                  borderRadius: "8px",
                  marginBottom: "12px",
                  fontSize: "0.92rem",
                  lineHeight: "1.4"
                }}
              >
                ⚠️{" "}
                <strong>
                  {lang === "hi"
                    ? "नमूना / असत्यापित डेटा:"
                    : lang === "kn"
                    ? "ಮಾದರಿ / ಪರಿಶೀಲಿಸದ ಮಾಹಿತಿ:"
                    : "Sample / Unverified Data:"}
                </strong>{" "}
                {lang === "hi"
                  ? "यह सलाह प्रारंभिक या गैर-सत्यापित रिकॉर्ड पर आधारित है। कृपया स्थानीय KVK या कृषि अधिकारी से पुष्टि करें।"
                  : lang === "kn"
                  ? "ಈ ಸಲಹೆಯು ಅಪೂರ್ಣ ಅಥವಾ ಪರಿಶೀಲಿಸದ ದಾಖಲೆಗಳನ್ನು ಆಧರಿಸಿದೆ. ಸ್ಥಳೀಯ KVK ಅನ್ನು ಸಂಪರ್ಕಿಸಿ."
                  : "This guidance is based on experimental or unverified sources. Please consult your local KVK or Kisan Call Centre before application."}
              </div>
            )}

            <p className="farmer-answer-text">
              {lastAssistantMessage.isExpanded
                ? lastAssistantMessage.fullText || lastAssistantMessage.text
                : lastAssistantMessage.shortText || lastAssistantMessage.text}
            </p>

            {/* Honest Engine & Fallback Labeling (Ground Rule 3) */}
            {currentResponse && (
              <div
                style={{
                  marginTop: "8px",
                  fontSize: "0.78rem",
                  color: "#6c757d",
                  display: "flex",
                  gap: "8px",
                  flexWrap: "wrap"
                }}
              >
                {currentResponse.engine_used && (
                  <span style={{ background: "#e9ecef", padding: "2px 8px", borderRadius: "12px" }}>
                    ⚙️ Engine: {currentResponse.engine_used}
                  </span>
                )}
                {currentResponse.is_fallback && (
                  <span style={{ background: "#fff3cd", color: "#856404", padding: "2px 8px", borderRadius: "12px" }}>
                    ⚡ Fallback Mode
                  </span>
                )}
              </div>
            )}

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
