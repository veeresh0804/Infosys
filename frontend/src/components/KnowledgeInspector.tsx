"use client";

import React, { useState } from "react";
import { RetrievedChunk, api } from "../lib/api";

interface KnowledgeInspectorProps {
  chunks: RetrievedChunk[];
  onReindexed?: () => void;
}

export const KnowledgeInspector: React.FC<KnowledgeInspectorProps> = ({ chunks, onReindexed }) => {
  const [isReindexing, setIsReindexing] = useState(false);
  const [reindexMsg, setReindexMsg] = useState<string | null>(null);

  const handleReindex = async () => {
    setIsReindexing(true);
    setReindexMsg(null);
    try {
      const res = await api.reindexKB();
      setReindexMsg(`Indexed ${res.chunks_created} chunks into ${res.vector_db_type}`);
      if (onReindexed) onReindexed();
    } catch (err: any) {
      setReindexMsg(`Error: ${err.message}`);
    } finally {
      setIsReindexing(false);
    }
  };

  return (
    <div className="inspector-card">
      <div className="inspector-header">
        <div>
          <h3>📚 Knowledge Base & Retrieval Inspector</h3>
          <p className="inspector-subtitle">
            Inspect embedded chunks retrieved from ICAR, KCC FAQs & Govt Schemes.
          </p>
        </div>
        <button
          onClick={handleReindex}
          disabled={isReindexing}
          className="btn-secondary"
        >
          {isReindexing ? "⏳ Indexing..." : "🔄 Re-index Knowledge Base"}
        </button>
      </div>

      {reindexMsg && <div className="notice-banner">{reindexMsg}</div>}

      {chunks && chunks.length > 0 ? (
        <div className="chunks-list">
          {chunks.map((chunk, idx) => (
            <div key={chunk.id || idx} className="chunk-item">
              <div className="chunk-header">
                <span className="badge badge-source">{chunk.source}</span>
                <span className="badge badge-score">
                  Similarity: {(chunk.similarity_score * 100).toFixed(1)}%
                </span>
              </div>
              <pre className="chunk-content">{chunk.content}</pre>
            </div>
          ))}
        </div>
      ) : (
        <p className="empty-notice">
          No knowledge-base chunks retrieved for this query (Query was handled via live data sub-agent or no matches found).
        </p>
      )}
    </div>
  );
};
