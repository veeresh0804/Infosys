"use client";

import React, { useState, useRef } from "react";

interface AudioRecorderProps {
  onAudioReady: (base64Audio: string) => void;
  disabled?: boolean;
}

export const AudioRecorder: React.FC<AudioRecorderProps> = ({ onAudioReady, disabled }) => {
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const timerRef = useRef<NodeJS.Timeout | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);

  const startRecording = async () => {
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

      mediaRecorder.onstop = () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/wav" });
        const reader = new FileReader();
        reader.onloadend = () => {
          const base64Data = (reader.result as string).split(",")[1];
          onAudioReady(base64Data);
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
