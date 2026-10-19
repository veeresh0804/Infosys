"use client";

import React, { useState, useRef } from "react";

interface AudioRecorderProps {
  onAudioReady: (base64Audio: string, mime: string, filename: string) => void;
  disabled?: boolean;
}

function getBestSupportedAudioMime(): { mime: string; ext: string } {
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

export const AudioRecorder: React.FC<AudioRecorderProps> = ({ onAudioReady, disabled }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const selectedFormatRef = useRef<{ mime: string; ext: string }>({ mime: "audio/webm", ext: "webm" });

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      audioChunksRef.current = [];
      const format = getBestSupportedAudioMime();
      selectedFormatRef.current = format;

      const mediaRecorder = new MediaRecorder(stream, { mimeType: format.mime });
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: format.mime });
        const reader = new FileReader();
        reader.onloadend = () => {
          const base64Data = (reader.result as string).split(",")[1];
          onAudioReady(base64Data, format.mime, `voice_query.${format.ext}`);
        };
        reader.readAsDataURL(audioBlob);

        // Stop all mic tracks
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start();
      setIsRecording(true);
      setRecordingSeconds(0);
      timerRef.current = setInterval(() => {
        setRecordingSeconds((prev) => prev + 1);
      }, 1000);
    } catch (err) {
      console.error("Mic access denied or unavailable:", err);
      alert("Microphone access could not be acquired. You can also type your query directly.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (timerRef.current) clearInterval(timerRef.current);
    }
  };

  return (
    <div style={{ display: "inline-flex", alignItems: "center", gap: "8px" }}>
      {!isRecording ? (
        <button
          type="button"
          onClick={startRecording}
          disabled={disabled}
          className="btn-mic"
          title="Speak your question (Sarvam AI STT)"
        >
          🎤 Speak
        </button>
      ) : (
        <button
          type="button"
          onClick={stopRecording}
          className="btn-mic-recording"
          title="Stop Recording"
        >
          ⏹ Stop ({recordingSeconds}s)
        </button>
      )}
    </div>
  );
};
