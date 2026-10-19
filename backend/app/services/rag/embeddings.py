import logging
import hashlib
from typing import List
from backend.app.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    """
    Embedding service using sentence-transformers/all-MiniLM-L6-v2.
    Produces 384-dimensional dense vectors for semantic search in Pinecone and ChromaDB.
    """

    def __init__(self):
        self.model_name = settings.EMBEDDING_MODEL_NAME
        self._model = None
        self._loaded = False

    def _load_model(self):
        if self._model is not None or self._loaded:
            return
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading SentenceTransformer embedding model: {self.model_name}...")
            self._model = SentenceTransformer(self.model_name)
            self._loaded = True
            logger.info("SentenceTransformer model loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not load SentenceTransformer ({self.model_name}): {e}. Using deterministic hashing embedding fallback.")
            self._loaded = True

    def embed_text(self, text: str) -> List[float]:
        """
        Embeds a single string into a 384-dimensional vector.
        """
        self._load_model()
        if self._model is not None:
            try:
                emb = self._model.encode(text, convert_to_numpy=True)
                return emb.tolist()
            except Exception as e:
                logger.error(f"Error encoding with SentenceTransformer: {e}")

        # Deterministic 384-dimensional pseudo-embedding fallback
        return self._fallback_embed(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embeds multiple documents.
        """
        self._load_model()
        if self._model is not None:
            try:
                embs = self._model.encode(texts, convert_to_numpy=True)
                return embs.tolist()
            except Exception as e:
                logger.error(f"Error batch encoding with SentenceTransformer: {e}")

        return [self._fallback_embed(t) for t in texts]

    def _fallback_embed(self, text: str) -> List[float]:
        """
        Generates a normalized 384-dimensional vector based on text token hashing.
        """
        vec = [0.0] * 384
        for word in text.lower().split():
            h = int(hashlib.sha256(word.encode()).hexdigest(), 16)
            idx = h % 384
            val = ((h >> 8) % 1000) / 1000.0 - 0.5
            vec[idx] += val

        # Normalize vector
        magnitude = sum(x * x for x in vec) ** 0.5
        if magnitude > 0:
            vec = [round(x / magnitude, 6) for x in vec]
        else:
            vec[0] = 1.0
        return vec

embedding_service = EmbeddingService()
