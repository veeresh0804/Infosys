"use client";

import { useEffect, useRef, useState } from "react";

type Entity = {
  type: string;
  value: string;
};

type PipelineStep = {
  step: string;
  status: string;
  details: string;
};

type RetrievedRecord = {
  id: string;
  category: string;
  question: string;
  answer: string;
  source: string;
  source_url: string;
  score: number;
};

type QuestionResult = {
  session_id: string;
  original_question: string;
  detected_language: string;
  normalized_question: string;
  intent: string;
  entities: Entity[];
  retrieved_records: RetrievedRecord[];
  pipeline_steps: PipelineStep[];
  processing_status: string;
  message: string;
};

type HistoryItem = {
  id: string;
  question: string;
  language: string;
  result: QuestionResult;
  createdAt: string;
};

const API_URL = "http://127.0.0.1:8000";
const HISTORY_KEY = "agri-chatbot-history";

const LANGUAGES = [
  { value: "en", label: "English" },
  { value: "hi", label: "Hindi" },
  { value: "kn", label: "Kannada" },
  { value: "te", label: "Telugu" },
  { value: "ta", label: "Tamil" },
];

export default function Home() {
  const [question, setQuestion] = useState("");
  const [language, setLanguage] = useState("en");
  const [result, setResult] = useState<QuestionResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [backendStatus, setBackendStatus] = useState("Checking connection...");
  const [error, setError] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [voiceMessage, setVoiceMessage] = useState("");
  const [isGeneratingSpeech, setIsGeneratingSpeech] = useState(false);
  const [audioUrl, setAudioUrl] = useState("");
  const [searchHistory, setSearchHistory] = useState<HistoryItem[]>([]);
  const [showHistory, setShowHistory] = useState(true);
  const [historyReady, setHistoryReady] = useState(false);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef("");

  useEffect(() => {
    try {
      const saved = localStorage.getItem(HISTORY_KEY);

      if (saved) {
        const parsed: unknown = JSON.parse(saved);

        if (Array.isArray(parsed)) {
          setSearchHistory(parsed as HistoryItem[]);
        }
      }
    } catch {
      console.error("Could not load search history.");
    } finally {
      setHistoryReady(true);
    }
  }, []);

  useEffect(() => {
    if (!historyReady) return;

    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(searchHistory));
    } catch {
      console.error("Could not save search history.");
    }
  }, [searchHistory, historyReady]);

  useEffect(() => {
    void checkBackend();

    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
      audioRef.current?.pause();

      if (audioUrlRef.current) {
        URL.revokeObjectURL(audioUrlRef.current);
      }
    };
  }, []);

  async function checkBackend() {
    try {
      const response = await fetch(`${API_URL}/health`);

      if (!response.ok) {
        throw new Error("Backend health check failed.");
      }

      const data = await response.json();

      setBackendStatus(
        `Connected${
          typeof data.knowledge_base_records === "number"
            ? ` · ${data.knowledge_base_records} knowledge-base records`
            : ""
        }`
      );
    } catch {
      setBackendStatus("Backend disconnected. Start FastAPI on port 8000.");
    }
  }

  function getAnswerText(data: QuestionResult) {
    return (
      data.retrieved_records
        ?.map((record) => record.answer)
        .filter((answer) => Boolean(answer?.trim()))
        .join("\n\n") || ""
    );
  }

  function clearPreviousAudio() {
    audioRef.current?.pause();
    audioRef.current = null;

    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = "";
    }

    setAudioUrl("");
  }

  function saveToHistory(data: QuestionResult, originalQuestion: string) {
    const item: HistoryItem = {
      id:
        data.session_id ||
        `${Date.now()}-${Math.random().toString(36).slice(2)}`,
      question: originalQuestion,
      language,
      result: data,
      createdAt: new Date().toISOString(),
    };

    setSearchHistory((previous) =>
      [
        item,
        ...previous.filter(
          (entry) =>
            entry.question.toLowerCase() !== originalQuestion.toLowerCase()
        ),
      ].slice(0, 50)
    );
  }

  function openHistoryItem(item: HistoryItem) {
    setQuestion(item.question);
    setLanguage(item.language);
    setResult(item.result);
    setError("");
    setVoiceMessage("");
    clearPreviousAudio();

    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function deleteHistoryItem(id: string) {
    setSearchHistory((previous) =>
      previous.filter((item) => item.id !== id)
    );
  }

  function clearSearchHistory() {
    if (window.confirm("Delete all search history?")) {
      setSearchHistory([]);
    }
  }

  async function startRecording() {
    setError("");
    setVoiceMessage("");

    if (!navigator.mediaDevices?.getUserMedia || typeof window.MediaRecorder === "undefined") {
      setError("Audio recording is not supported in this browser.");
      return;
    }

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      chunksRef.current = [];

      const mediaRecorder =
        MediaRecorder.isTypeSupported("audio/webm")
          ? new MediaRecorder(stream, { mimeType: "audio/webm" })
          : new MediaRecorder(stream);

      recorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onerror = () => {
        setError("Recording failed. Please try again.");
        setIsRecording(false);
      };

      mediaRecorder.onstop = async () => {
        stream.getTracks().forEach((track) => track.stop());
        streamRef.current = null;

        const blob = new Blob(chunksRef.current, {
          type: mediaRecorder.mimeType || "audio/webm",
        });

        if (!blob.size) {
          setError("No audio was recorded. Please try again.");
          setIsRecording(false);
          return;
        }

        const formData = new FormData();
        formData.append(
          "audio",
          blob,
          blob.type.includes("mp4") ? "question.m4a" : "question.webm"
        );

        setIsTranscribing(true);
        setVoiceMessage("Converting your speech to text...");

        try {
          const response = await fetch(`${API_URL}/api/speech-to-text`, {
            method: "POST",
            body: formData,
          });

          const data = await response.json();

          if (!response.ok) {
            throw new Error(data.detail || "Speech recognition failed.");
          }

          const transcript = String(data.transcript || "").trim();

          if (!transcript) {
            throw new Error("No speech was detected. Please try again.");
          }

          setQuestion((previous) =>
            previous.trim() ? `${previous.trim()} ${transcript}` : transcript
          );
          setVoiceMessage(
            "Speech converted! Edit the question if needed, then click Ask Question."
          );
        } catch (err) {
          setError(
            err instanceof Error
              ? err.message
              : "Unable to transcribe audio."
          );
          setVoiceMessage("");
        } finally {
          setIsTranscribing(false);
          setIsRecording(false);
        }
      };

      mediaRecorder.start();
      setIsRecording(true);
      setVoiceMessage("Recording... Click Stop recording when you finish.");
    } catch {
      setError(
        "Microphone access was blocked. Allow microphone permission and try again."
      );
      setIsRecording(false);
    }
  }

  function stopRecording() {
    if (
      recorderRef.current &&
      recorderRef.current.state !== "inactive"
    ) {
      recorderRef.current.stop();
    }
  }

  async function speakAnswer(answerText: string) {
    if (!answerText.trim()) {
      setError("There is no answer available to read aloud.");
      return;
    }

    setIsGeneratingSpeech(true);
    setError("");
    setVoiceMessage("");

    try {
      const response = await fetch(`${API_URL}/api/text-to-speech`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: answerText.slice(0, 3500),
          language,
        }),
      });

      if (!response.ok) {
        let message = "Could not generate spoken answer.";

        try {
          const data = await response.json();
          message = data.detail || message;
        } catch {
          // Ignore JSON parse errors and keep the default message.
        }

        throw new Error(message);
      }

      const blob = await response.blob();

      if (!blob.size) {
        throw new Error("The speech service returned empty audio.");
      }

      clearPreviousAudio();

      const newUrl = URL.createObjectURL(blob);
      audioUrlRef.current = newUrl;
      setAudioUrl(newUrl);

      const audio = new Audio(newUrl);
      audioRef.current = audio;

      try {
        await audio.play();
      } catch {
        setVoiceMessage(
          "Audio is ready. Press Play below to hear the answer."
        );
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? `Speech generation failed: ${err.message}`
          : "Unable to generate speech."
      );
    } finally {
      setIsGeneratingSpeech(false);
    }
  }

  async function submitQuestion() {
    const submittedQuestion = question.trim();

    if (!submittedQuestion) {
      setError("Please enter an agricultural question.");
      setResult(null);
      return;
    }

    setLoading(true);
    setError("");
    setVoiceMessage("");
    setResult(null);
    clearPreviousAudio();

    try {
      const response = await fetch(`${API_URL}/api/process-question`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: submittedQuestion,
          language,
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "Question processing failed.");
      }

      const questionResult = data as QuestionResult;
      setResult(questionResult);
      saveToHistory(questionResult, submittedQuestion);

      const answerText = getAnswerText(questionResult);

      if (
        questionResult.processing_status === "retrieved" &&
        answerText
      ) {
        await speakAnswer(answerText);
      }
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Unable to process your question."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <main style={styles.page}>
      <header style={styles.header}>
        <div style={styles.emoji}>🌱</div>
        <h1 style={styles.title}>Multilingual Agricultural Chatbot</h1>
        <p style={styles.subtitle}>
          Your farming assistant for crop care, pests, soil health, and agricultural schemes.
        </p>
      </header>

      <section style={styles.card}>
        <h2 style={styles.heading}>Backend Connection</h2>
        <button onClick={() => void checkBackend()} style={styles.secondaryButton}>
          Test Backend Connection
        </button>
        {backendStatus && <p role="status" style={styles.status}>{backendStatus}</p>}
      </section>

      <section style={styles.card}>
        <div style={styles.headerRow}>
          <h2 style={styles.heading}>Ask Your Farming Question</h2>
          <button
            type="button"
            onClick={() => setShowHistory((current) => !current)}
            style={styles.historyToggle}
          >
            {showHistory ? "Hide history" : "Show history"}
          </button>
        </div>

        <label htmlFor="language" style={styles.label}>Question language</label>
        <select
          id="language"
          value={language}
          onChange={(event) => setLanguage(event.target.value)}
          style={styles.input}
        >
          {LANGUAGES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>

        <label htmlFor="question" style={styles.label}>Your question</label>
        <textarea
          id="question"
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && !loading) {
              event.preventDefault();
              void submitQuestion();
            }
          }}
          placeholder="Example: How can I protect my rice crop from pests?"
          rows={4}
          style={styles.textarea}
        />

        <div style={styles.buttonRow}>
          {!isRecording ? (
            <button
              type="button"
              onClick={() => void startRecording()}
              disabled={isTranscribing || loading}
              style={styles.secondaryButton}
            >
              {isTranscribing ? "Transcribing..." : "🎙️ Record question"}
            </button>
          ) : (
            <button type="button" onClick={stopRecording} style={styles.stopButton}>
              ⏹ Stop recording
            </button>
          )}

          <button
            type="button"
            onClick={() => void submitQuestion()}
            disabled={loading || isRecording || isTranscribing}
            style={{
              ...styles.primaryButton,
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? "Processing question..." : "Ask Question"}
          </button>
        </div>

        {voiceMessage && <p role="status" style={styles.status}>{voiceMessage}</p>}
        <p style={styles.hint}>
          You can type a question or record it. Review the transcript before submitting.
        </p>
        {error && <p role="alert" style={styles.error}>{error}</p>}
      </section>

      {showHistory && (
        <section style={styles.card}>
          <div style={styles.historyHeader}>
            <h2 style={styles.heading}>Recent History</h2>
            {searchHistory.length > 0 && (
              <button type="button" onClick={clearSearchHistory} style={styles.inlineButton}>
                Clear all
              </button>
            )}
          </div>

          {!historyReady ? (
            <p style={styles.hint}>Loading history...</p>
          ) : searchHistory.length === 0 ? (
            <p style={styles.hint}>No saved questions yet.</p>
          ) : (
            <div style={styles.historyList}>
              {searchHistory.map((item) => (
                <div key={item.id} style={styles.historyItem}>
                  <button
                    type="button"
                    onClick={() => openHistoryItem(item)}
                    style={styles.historyButton}
                  >
                    <span style={styles.historyQuestion}>{item.question}</span>
                    <span style={styles.historyMeta}>
                      {item.language.toUpperCase()} · {new Date(item.createdAt).toLocaleString()}
                    </span>
                  </button>
                  <button
                    type="button"
                    onClick={() => deleteHistoryItem(item.id)}
                    aria-label={`Delete ${item.question}`}
                    style={styles.deleteButton}
                  >
                    Delete
                  </button>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {result && (
        <>
          <section style={styles.resultCard}>
            <h2 style={styles.heading}>🌾 Agricultural Answer</h2>
            <p>
              <strong>Your question:</strong> {result.original_question}
            </p>
            <p>
              <strong>Processing status:</strong> {result.processing_status}
            </p>
            <p>{result.message}</p>

            {result.retrieved_records.length > 0 ? (
              result.retrieved_records.map((record, index) => (
                <article key={record.id || index} style={styles.answerCard}>
                  <p style={styles.category}>
                    {(record.category || "Agriculture").replaceAll("_", " ")}
                  </p>
                  <h3 style={styles.answerTitle}>{record.question || "Related information"}</h3>
                  <p style={styles.answerText}>{record.answer}</p>
                  <p style={styles.source}>
                    <strong>Source:</strong> {record.source}
                  </p>
                  {record.source_url && (
                    <a
                      href={record.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={styles.link}
                    >
                      View source ↗
                    </a>
                  )}
                </article>
              ))
            ) : (
              <p>
                No matching information was found. Try asking about crop pests, soil health,
                crop management, or government schemes.
              </p>
            )}

            {result.retrieved_records.some((record) => Boolean(record.answer?.trim())) && (
              <div style={styles.speechBox}>
                <h3 style={styles.answerTitle}>🔊 Listen to the answer</h3>
                <button
                  type="button"
                  onClick={() => void speakAnswer(getAnswerText(result))}
                  disabled={isGeneratingSpeech}
                  style={{
                    ...styles.primaryButton,
                    opacity: isGeneratingSpeech ? 0.7 : 1,
                  }}
                >
                  {isGeneratingSpeech ? "Generating speech..." : "Generate spoken answer"}
                </button>
                {audioUrl && <audio controls src={audioUrl} style={styles.audioPlayer} />}
                <p style={styles.hint}>
                  Current speech output is in English. Multilingual speech can be added next.
                </p>
              </div>
            )}
          </section>

          <section style={styles.card}>
            <h2 style={styles.heading}>Question Analysis</h2>
            <p>
              <strong>Detected intent:</strong> {result.intent.replaceAll("_", " ")}
            </p>
            <p>
              <strong>Language field:</strong> {result.detected_language}
            </p>

            <h3>Detected Entities</h3>
            {result.entities.length > 0 ? (
              <ul>
                {result.entities.map((entity, index) => (
                  <li key={`${entity.type}-${index}`}>
                    {entity.type}: {entity.value}
                  </li>
                ))}
              </ul>
            ) : (
              <p>No entities detected.</p>
            )}

            <h3>Processing Pipeline</h3>
            <ol style={styles.pipeline}>
              {result.pipeline_steps.map((step, index) => (
                <li key={`${step.step}-${index}`} style={styles.pipelineItem}>
                  <strong>{step.step.replaceAll("_", " ")}</strong>
                  <span style={styles.stepStatus}>{step.status}</span>
                  <p style={styles.stepDetails}>{step.details}</p>
                </li>
              ))}
            </ol>

            <p style={styles.session}>Session ID: {result.session_id}</p>
          </section>
        </>
      )}

      <footer style={styles.footer}>Agricultural Chatbot Project</footer>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    fontFamily: "Arial, sans-serif",
    maxWidth: "820px",
    margin: "0 auto",
    padding: "28px 18px",
    color: "#1f2937",
    backgroundColor: "#f8faf8",
    minHeight: "100vh",
    lineHeight: 1.6,
  },
  header: { textAlign: "center", marginBottom: "30px" },
  headerRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "12px",
    marginBottom: "8px",
  },
  emoji: { fontSize: "42px" },
  title: { color: "#166534", fontSize: "30px", lineHeight: 1.25 },
  subtitle: { color: "#526052" },
  card: {
    backgroundColor: "#ffffff",
    border: "1px solid #dce5dc",
    borderRadius: "14px",
    padding: "22px",
    marginBottom: "22px",
  },
  resultCard: {
    backgroundColor: "#f0fdf4",
    border: "1px solid #bbf7d0",
    borderRadius: "14px",
    padding: "22px",
    marginBottom: "22px",
  },
  heading: { color: "#166534", marginTop: 0 },
  label: {
    display: "block",
    fontWeight: 600,
    marginTop: "14px",
    marginBottom: "6px",
  },
  input: {
    display: "block",
    width: "100%",
    boxSizing: "border-box",
    padding: "12px",
    border: "1px solid #cbd5cb",
    borderRadius: "8px",
    fontSize: "16px",
    backgroundColor: "#ffffff",
  },
  textarea: {
    display: "block",
    width: "100%",
    boxSizing: "border-box",
    padding: "12px",
    border: "1px solid #cbd5cb",
    borderRadius: "8px",
    fontSize: "16px",
    resize: "vertical",
    marginTop: "6px",
  },
  primaryButton: {
    width: "100%",
    padding: "13px 18px",
    backgroundColor: "#166534",
    color: "#ffffff",
    border: "none",
    borderRadius: "8px",
    cursor: "pointer",
    fontSize: "16px",
    marginTop: "14px",
  },
  secondaryButton: {
    padding: "11px 16px",
    backgroundColor: "#e7f4e8",
    color: "#166534",
    border: "1px solid #bbf7d0",
    borderRadius: "8px",
    cursor: "pointer",
    fontSize: "15px",
    marginTop: "14px",
  },
  stopButton: {
    padding: "11px 16px",
    backgroundColor: "#fff1f2",
    color: "#9f1239",
    border: "1px solid #fecdd3",
    borderRadius: "8px",
    cursor: "pointer",
    fontSize: "15px",
    marginTop: "14px",
  },
  historyToggle: {
    border: "1px solid #d1d5db",
    borderRadius: "8px",
    padding: "8px 12px",
    backgroundColor: "#f8fafc",
    color: "#166534",
    cursor: "pointer",
  },
  buttonRow: {
    display: "flex",
    gap: "12px",
    flexWrap: "wrap",
    alignItems: "center",
  },
  status: { color: "#166534", overflowWrap: "anywhere" },
  hint: { color: "#64748b", fontSize: "13px" },
  error: {
    color: "#b91c1c",
    backgroundColor: "#fef2f2",
    padding: "10px",
    borderRadius: "8px",
  },
  historyHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: "12px",
  },
  inlineButton: {
    border: "none",
    background: "transparent",
    color: "#166534",
    cursor: "pointer",
    fontWeight: 600,
  },
  historyList: {
    display: "flex",
    flexDirection: "column",
    gap: "12px",
  },
  historyItem: {
    display: "flex",
    alignItems: "stretch",
    gap: "8px",
    width: "100%",
  },
  historyButton: {
    flex: 1,
    backgroundColor: "#f8fafc",
    border: "1px solid #dbe7db",
    borderRadius: "10px",
    textAlign: "left",
    padding: "12px 14px",
    cursor: "pointer",
    display: "flex",
    flexDirection: "column",
    gap: "4px",
  },
  historyQuestion: {
    color: "#111827",
    fontWeight: 600,
    overflowWrap: "anywhere",
  },
  historyMeta: {
    color: "#64748b",
    fontSize: "12px",
  },
  deleteButton: {
    border: "1px solid #fecaca",
    backgroundColor: "#fff1f2",
    color: "#b91c1c",
    borderRadius: "8px",
    padding: "8px 10px",
    cursor: "pointer",
  },
  answerCard: {
    backgroundColor: "#ffffff",
    border: "1px solid #d1e7d5",
    borderRadius: "10px",
    padding: "18px",
    marginTop: "16px",
  },
  category: {
    color: "#166534",
    fontSize: "13px",
    textTransform: "capitalize",
    fontWeight: 700,
  },
  answerTitle: { marginBottom: "8px" },
  answerText: { whiteSpace: "pre-wrap" },
  source: { fontSize: "14px", color: "#475569" },
  link: { color: "#166534", fontWeight: 600 },
  speechBox: {
    marginTop: "24px",
    paddingTop: "18px",
    borderTop: "1px solid #d1e7d5",
  },
  audioPlayer: { display: "block", width: "100%", marginTop: "14px" },
  pipeline: { paddingLeft: "22px" },
  pipelineItem: { marginBottom: "18px" },
  stepStatus: {
    marginLeft: "10px",
    padding: "3px 8px",
    backgroundColor: "#dcfce7",
    color: "#166534",
    borderRadius: "6px",
    fontSize: "12px",
  },
  stepDetails: { marginTop: "4px", color: "#526052" },
  session: { fontSize: "12px", color: "#64748b", overflowWrap: "anywhere" },
  footer: { textAlign: "center", color: "#64748b", fontSize: "13px", padding: "10px" },
};
