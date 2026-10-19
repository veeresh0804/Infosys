"use client";

import React, { useState } from "react";
import { AudioRecorder } from "./AudioRecorder";
import { QueryResponse, api } from "../lib/api";

interface ChatMessage {
  id: string;
  sender: "farmer" | "assistant";
  text: string;
  responseMeta?: QueryResponse;
}

interface ChatInterfaceProps {
  sessionId: string;
  selectedLanguage: string;
  onLanguageChange: (lang: string) => void;
  onQueryComplete: (res: QueryResponse) => void;
}

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  sessionId,
  selectedLanguage,
  onLanguageChange,
  onQueryComplete
}) => {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      sender: "assistant",
      text: "Namaste! I am your AI Smart Farming Assistant. You can ask agricultural questions in Hindi (हिंदी), Kannada (ಕನ್ನಡ), or English by typing or using the microphone button below."
    }
  ]);
  const [inputText, setInputText] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [audioPlayingId, setAudioPlayingId] = useState<string | null>(null);

  const handleSend = async (textToSend?: string, audioBase64?: string) => {
    const text = textToSend !== undefined ? textToSend : inputText;
    if (!text && !audioBase64) return;

    const userMsgId = "msg-" + Date.now();
    const userMsg: ChatMessage = {
      id: userMsgId,
      sender: "farmer",
      text: text || "🎤 [Voice Query Recorded]"
    };

    setMessages((prev) => [...prev, userMsg]);
    setInputText("");
    setIsLoading(true);

    try {
      const response = await api.queryPipeline({
        sessionId,
        text: text || undefined,
        language: selectedLanguage,
        audioBase64
      });

      const assistantMsg: ChatMessage = {
        id: "resp-" + Date.now(),
        sender: "assistant",
        text: response.answer_translated,
        responseMeta: response
      };

      setMessages((prev) => [...prev, assistantMsg]);
      onQueryComplete(response);
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: "err-" + Date.now(),
          sender: "assistant",
          text: `⚠️ Query processing error: ${err.message}`
        }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const playTTS = async (msgId: string, text: string, lang: string) => {
    setAudioPlayingId(msgId);
    try {
      const audioB64 = await api.synthesizeSpeech(text, lang);
      if (audioB64) {
        const audio = new Audio("data:audio/wav;base64," + audioB64);
        audio.onended = () => setAudioPlayingId(null);
        audio.onerror = () => setAudioPlayingId(null);
        await audio.play();
      } else {
        setAudioPlayingId(null);
      }
    } catch (e) {
      console.error("TTS playback error", e);
      setAudioPlayingId(null);
    }
  };

  // Sample prompt chips for immediate testing
  const samplePrompts = [
    { label: "Tomato leaf curl (Hindi)", text: "टमाटर की फसल में पत्ता मरोड़ रोग का क्या उपाय है?", lang: "hi" },
    { label: "Paddy stem borer (Kannada)", text: "ಭತ್ತದಲ್ಲಿ ಕಾಂಡ ಕೊರೆಯುವ ಹುಳುವಿನ ಹಾನಿಯನ್ನು ಹೇಗೆ ನಿಯಂತ್ರಿಸುವುದು?", lang: "kn" },
    { label: "Mandi price (English)", text: "What is today's mandi price for Tomato in Karnataka?", lang: "en" },
    { label: "Weather advisory (Hindi)", text: "क्या आज बारिश होगी? छिड़काव कर सकते हैं क्या?", lang: "hi" },
    { label: "PM-KISAN eligibility (English)", text: "Am I eligible for PM-KISAN subsidy with 2 acres land?", lang: "en" }
  ];

  return (
    <div className="chat-card">
      <div className="chat-topbar">
        <div className="lang-selector-group">
          <label>🌐 Input / Voice Language:</label>
          <div className="lang-buttons">
            <button
              className={`lang-btn ${selectedLanguage === "hi" ? "active" : ""}`}
              onClick={() => onLanguageChange("hi")}
            >
              हिन्दी (Hindi)
            </button>
            <button
              className={`lang-btn ${selectedLanguage === "kn" ? "active" : ""}`}
              onClick={() => onLanguageChange("kn")}
            >
              ಕನ್ನಡ (Kannada)
            </button>
            <button
              className={`lang-btn ${selectedLanguage === "en" ? "active" : ""}`}
              onClick={() => onLanguageChange("en")}
            >
              English
            </button>
          </div>
        </div>
      </div>

      <div className="samples-row">
        <small style={{ color: "#666" }}>Try quick sample prompts:</small>
        <div className="chips-container">
          {samplePrompts.map((p, idx) => (
            <button
              key={idx}
              className="chip-btn"
              onClick={() => {
                onLanguageChange(p.lang);
                handleSend(p.text);
              }}
            >
              {p.label}
            </button>
          ))}
        </div>
      </div>

      <div className="messages-stream">
        {messages.map((msg) => (
          <div key={msg.id} className={`message-row ${msg.sender}`}>
            <div className={`message-bubble ${msg.sender}`}>
              <div className="message-content">{msg.text}</div>

              {msg.responseMeta && (
                <div className="telemetry-panel">
                  <div className="telemetry-header">
                    <span>⚡ Pipeline Telemetry:</span>
                    {msg.responseMeta.is_low_confidence ? (
                      <span className="badge badge-flagged">
                        🚩 Low Confidence (Score: {(msg.responseMeta.confidence_score * 100).toFixed(0)}%) - Flagged for Extension Review
                      </span>
                    ) : (
                      <span className="badge badge-high-confidence">
                        ✓ High Quality (Score: {(msg.responseMeta.confidence_score * 100).toFixed(0)}%)
                      </span>
                    )}
                  </div>

                  <div className="telemetry-tags">
                    <span className="tag">
                      <strong>Detected Language:</strong> {msg.responseMeta.detected_language}
                    </span>
                    <span className="tag">
                      <strong>Intent:</strong> {msg.responseMeta.intent} ({(msg.responseMeta.intent_confidence * 100).toFixed(0)}%)
                    </span>
                    <span className="tag">
                      <strong>Sub-Agent:</strong> {msg.responseMeta.sub_agent}
                    </span>
                  </div>

                  <div className="canonical-preview">
                    <strong>Canonical English:</strong> "{msg.responseMeta.canonical_query}"
                  </div>

                  {msg.responseMeta.entities && msg.responseMeta.entities.length > 0 && (
                    <div className="entities-list">
                      <strong>Entities:</strong>{" "}
                      {msg.responseMeta.entities.map((ent, idx) => (
                        <span key={idx} className="entity-badge">
                          {ent.label}: {ent.text}
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="audio-action-row">
                    <button
                      className="btn-audio-play"
                      onClick={() =>
                        playTTS(
                          msg.id,
                          msg.text,
                          msg.responseMeta?.detected_language || selectedLanguage
                        )
                      }
                      disabled={audioPlayingId === msg.id}
                    >
                      {audioPlayingId === msg.id ? "🔊 Playing..." : "🔊 Play Voice Answer (Sarvam TTS)"}
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {isLoading && (
          <div className="message-row assistant">
            <div className="message-bubble assistant loading">
              <span className="spinner">🌱</span> Synthesizing verified agricultural advisory...
            </div>
          </div>
        )}
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          handleSend();
        }}
        className="chat-input-bar"
      >
        <AudioRecorder
          onAudioReady={(base64Audio) => handleSend("", base64Audio)}
          disabled={isLoading}
        />
        <input
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          placeholder={`Type a question in ${selectedLanguage === "hi" ? "Hindi" : selectedLanguage === "kn" ? "Kannada" : "English"}...`}
          className="chat-text-input"
          disabled={isLoading}
        />
        <button type="submit" disabled={isLoading || !inputText.trim()} className="btn-send">
          Send ➤
        </button>
      </form>
    </div>
  );
};
