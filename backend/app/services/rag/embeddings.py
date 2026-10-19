import logging
import hashlib
from typing import List
from backend.app.config import settings

logger = logging.getLogger(__name__)

class EmbeddingService:
    """
    Lightweight embedding service using fastembed (ONNX runtime) with sentence-transformers/all-MiniLM-L6-v2.
    Produces 384-dimensional dense vectors fitting in < 512 MB RAM without torch.
    """

    def __init__(self):
        self.model_name = settings.EMBEDDING_MODEL_NAME
        self._fastembed_model = None
        self._st_model = None
        self._loaded = False
        self.engine_used = "uninitialized"

    def _load_model(self):
        if self._loaded:
            return

        # 1. Primary: FastEmbed (ONNX Runtime, no PyTorch needed, <50MB RAM)
        try:
            from fastembed import TextEmbedding
            logger.info("Loading FastEmbed ONNX embedding model (sentence-transformers/all-MiniLM-L6-v2)...")
            self._fastembed_model = TextEmbedding(model_name="sentence-transformers/all-MiniLM-L6-v2")
            self._loaded = True
            self.engine_used = "fastembed_onnx"
            logger.info("FastEmbed ONNX model loaded successfully.")
            return
        except Exception as e:
            logger.warning(f"FastEmbed not available ({e}). Trying SentenceTransformers...")

        # 2. Secondary: SentenceTransformer (if installed locally)
        try:
            from sentence_transformers import SentenceTransformer
            logger.info(f"Loading SentenceTransformer embedding model: {self.model_name}...")
            self._st_model = SentenceTransformer(self.model_name)
            self._loaded = True
            self.engine_used = "sentence_transformers"
            logger.info("SentenceTransformer model loaded successfully.")
            return
        except Exception as e:
            logger.warning(f"SentenceTransformers not available ({e}). Using deterministic token hashing fallback.")

        # 3. Fallback: Token hashing
        self._loaded = True
        self.engine_used = "token_hash_fallback"

    def embed_text(self, text: str) -> List[float]:
        """
        Embeds a single string into a 384-dimensional vector.
        """
        self._load_model()
        if self._fastembed_model is not None:
            try:
                embeddings = list(self._fastembed_model.embed([text]))
                return [round(float(v), 6) for v in embeddings[0]]
            except Exception as e:
                logger.error(f"Error encoding with FastEmbed: {e}")

        if self._st_model is not None:
            try:
                emb = self._st_model.encode(text, convert_to_numpy=True)
                return [round(float(v), 6) for v in emb.tolist()]
            except Exception as e:
                logger.error(f"Error encoding with SentenceTransformer: {e}")

        return self._fallback_embed(text)

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        Embeds multiple documents.
        """
        self._load_model()
        if self._fastembed_model is not None:
            try:
                embeddings = list(self._fastembed_model.embed(texts))
                return [[round(float(v), 6) for v in emb] for emb in embeddings]
            except Exception as e:
                logger.error(f"Error batch encoding with FastEmbed: {e}")

        if self._st_model is not None:
            try:
                embs = self._st_model.encode(texts, convert_to_numpy=True)
                return [[round(float(v), 6) for v in emb] for emb in embs.tolist()]
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
