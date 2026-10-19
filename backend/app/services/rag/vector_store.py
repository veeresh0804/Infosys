import os
import json
import logging
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod
from backend.app.config import settings
from backend.app.models.schemas import RetrievedChunk
from backend.app.services.rag.embeddings import embedding_service

logger = logging.getLogger(__name__)

class BaseVectorStore(ABC):
    @abstractmethod
    async def add_documents(self, documents: List[Dict[str, Any]]) -> int:
        pass

    @abstractmethod
    async def similarity_search(self, query: str, top_k: int = 3) -> List[RetrievedChunk]:
        pass

    @abstractmethod
    def count(self) -> int:
        pass

# ==============================================================================
# Pinecone Implementation
# ==============================================================================

class PineconeVectorStore(BaseVectorStore):
    def __init__(self):
        self.api_key = settings.PINECONE_API_KEY
        self.index_name = settings.PINECONE_INDEX_NAME
        self.cloud = settings.PINECONE_CLOUD
        self.region = settings.PINECONE_REGION
        self._index = None
        self._fallback_store = None

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key.strip() and not self.api_key.startswith("your_"))

    def _init_pinecone(self):
        if self._index is not None or not self.is_configured:
            return

        try:
            from pinecone import Pinecone, ServerlessSpec
            pc = Pinecone(api_key=self.api_key)
            existing_indexes = [idx.name for idx in pc.list_indexes()]

            if self.index_name not in existing_indexes:
                logger.info(f"Creating Pinecone index '{self.index_name}' with 384 dimensions...")
                pc.create_index(
                    name=self.index_name,
                    dimension=384,
                    metric="cosine",
                    spec=ServerlessSpec(cloud=self.cloud, region=self.region)
                )

            self._index = pc.Index(self.index_name)
            logger.info(f"Pinecone index '{self.index_name}' connected successfully.")
        except Exception as e:
            logger.warning(f"Pinecone connection failed: {e}. Falling back to local vector storage.")
            self._index = None

    async def add_documents(self, documents: List[Dict[str, Any]]) -> int:
        self._init_pinecone()
        if self._index is not None:
            vectors_to_upsert = []
            for doc in documents:
                doc_id = doc["id"]
                text = doc["content"]
                metadata = doc.get("metadata", {})
                metadata["text"] = text[:1000]
                metadata["source"] = doc.get("source", "Knowledge Base")

                emb = embedding_service.embed_text(text)
                vectors_to_upsert.append((doc_id, emb, metadata))

            # Batch upsert to Pinecone
            batch_size = 50
            for i in range(0, len(vectors_to_upsert), batch_size):
                batch = vectors_to_upsert[i:i + batch_size]
                self._index.upsert(vectors=batch)
            return len(vectors_to_upsert)

        # Fallback to local storage
        logger.info("[MOCK/LOCAL] Pinecone unavailable. Indexing in local vector fallback.")
        return await self._get_fallback_store().add_documents(documents)

    async def similarity_search(self, query: str, top_k: int = 3) -> List[RetrievedChunk]:
        self._init_pinecone()
        if self._index is not None:
            try:
                query_emb = embedding_service.embed_text(query)
                res = self._index.query(vector=query_emb, top_k=top_k, include_metadata=True)
                results = []
                for match in res.get("matches", []):
                    meta = match.get("metadata", {})
                    results.append(RetrievedChunk(
                        id=str(match.get("id")),
                        content=meta.get("text", ""),
                        source=meta.get("source", "Pinecone Index"),
                        similarity_score=round(float(match.get("score", 0.8)), 3),
                        metadata=meta
                    ))
                return results
            except Exception as e:
                logger.error(f"Pinecone query error: {e}")

        return await self._get_fallback_store().similarity_search(query, top_k)

    def count(self) -> int:
        self._init_pinecone()
        if self._index is not None:
            try:
                stats = self._index.describe_index_stats()
                return int(stats.get("total_vector_count", 0))
            except Exception:
                pass
        return self._get_fallback_store().count()

    def _get_fallback_store(self) -> BaseVectorStore:
        if self._fallback_store is None:
            self._fallback_store = LocalFallbackVectorStore()
        return self._fallback_store

# ==============================================================================
# ChromaDB Implementation
# ==============================================================================

class ChromaDBVectorStore(BaseVectorStore):
    def __init__(self):
        self.persist_dir = settings.CHROMA_PERSIST_DIRECTORY
        self.collection_name = settings.CHROMA_COLLECTION_NAME
        self._collection = None

    def _init_chroma(self):
        if self._collection is not None:
            return
        try:
            import chromadb
            os.makedirs(self.persist_dir, exist_ok=True)
            client = chromadb.PersistentClient(path=self.persist_dir)
            self._collection = client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"}
            )
            logger.info(f"ChromaDB collection '{self.collection_name}' initialized.")
        except Exception as e:
            logger.warning(f"ChromaDB initialization error: {e}. Using local memory vector store.")
            self._collection = None

    async def add_documents(self, documents: List[Dict[str, Any]]) -> int:
        self._init_chroma()
        if self._collection is not None:
            ids = [d["id"] for d in documents]
            docs = [d["content"] for d in documents]
            metadatas = [d.get("metadata", {}) for d in documents]
            embeddings = [embedding_service.embed_text(d["content"]) for d in documents]

            self._collection.upsert(
                ids=ids,
                documents=docs,
                metadatas=metadatas,
                embeddings=embeddings
            )
            return len(documents)
        return await LocalFallbackVectorStore().add_documents(documents)

    async def similarity_search(self, query: str, top_k: int = 3) -> List[RetrievedChunk]:
        self._init_chroma()
        if self._collection is not None:
            try:
                query_emb = embedding_service.embed_text(query)
                results = self._collection.query(
                    query_embeddings=[query_emb],
                    n_results=top_k
                )
                chunks = []
                if results and "documents" in results and results["documents"]:
                    doc_list = results["documents"][0]
                    id_list = results["ids"][0]
                    meta_list = results["metadatas"][0]
                    dist_list = results.get("distances", [[0.2] * len(doc_list)])[0]

                    for doc, doc_id, meta, dist in zip(doc_list, id_list, meta_list, dist_list):
                        similarity = max(0.0, min(1.0, 1.0 - dist))
                        chunks.append(RetrievedChunk(
                            id=doc_id,
                            content=doc,
                            source=meta.get("source", "ChromaDB"),
                            similarity_score=round(similarity, 3),
                            metadata=meta
                        ))
                    return chunks
            except Exception as e:
                logger.error(f"Chroma query error: {e}")
        return await LocalFallbackVectorStore().similarity_search(query, top_k)

    def count(self) -> int:
        self._init_chroma()
        if self._collection is not None:
            try:
                return self._collection.count()
            except Exception:
                pass
        return LocalFallbackVectorStore().count()

# ==============================================================================
# In-Memory / File-backed Fallback Vector Store
# ==============================================================================

class LocalFallbackVectorStore(BaseVectorStore):
    """
    Self-contained cosine-similarity vector store stored in data/local_vector_index.json
    Guarantees 100% functionality without cloud dependencies or external daemon.
    """
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LocalFallbackVectorStore, cls).__new__(cls)
            cls._instance._docs = []
            cls._instance._load_file()
        return cls._instance

    def _file_path(self) -> str:
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        return os.path.join(base_dir, "data", "local_vector_index.json")

    def _load_file(self):
        path = self._file_path()
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._docs = json.load(f)
            except Exception:
                self._docs = []

    def _save_file(self):
        path = self._file_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._docs, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to persist local vector index: {e}")

    async def add_documents(self, documents: List[Dict[str, Any]]) -> int:
        for d in documents:
            emb = embedding_service.embed_text(d["content"])
            # Remove existing by ID
            self._docs = [x for x in self._docs if x["id"] != d["id"]]
            self._docs.append({
                "id": d["id"],
                "content": d["content"],
                "source": d.get("source", "Knowledge Base"),
                "metadata": d.get("metadata", {}),
                "embedding": emb
            })
        self._save_file()
        return len(documents)

    async def similarity_search(self, query: str, top_k: int = 3) -> List[RetrievedChunk]:
        if not self._docs:
            return []

        q_emb = embedding_service.embed_text(query)

        def cosine_similarity(v1, v2):
            dot = sum(a * b for a, b in zip(v1, v2))
            norm1 = sum(a * a for a in v1) ** 0.5
            norm2 = sum(b * b for b in v2) ** 0.5
            return dot / (norm1 * norm2) if (norm1 > 0 and norm2 > 0) else 0.0

        scored = []
        for d in self._docs:
            score = cosine_similarity(q_emb, d["embedding"])
            # Keyword bonus for direct query token matches
            q_words = set(query.lower().split())
            d_words = set(d["content"].lower().split())
            overlap = len(q_words & d_words)
            boosted_score = min(1.0, score + overlap * 0.05)
            scored.append((boosted_score, d))

        scored.sort(key=lambda x: x[0], reverse=True)
        top = scored[:top_k]

        return [
            RetrievedChunk(
                id=d["id"],
                content=d["content"],
                source=d.get("source", "Local Vector Store"),
                similarity_score=round(score, 3),
                metadata=d.get("metadata", {})
            )
            for score, d in top
        ]

    def count(self) -> int:
        return len(self._docs)

def get_vector_store() -> BaseVectorStore:
    vtype = settings.VECTOR_DB_TYPE.lower()
    if vtype == "pinecone":
        return PineconeVectorStore()
    elif vtype == "chromadb":
        return ChromaDBVectorStore()
    return LocalFallbackVectorStore()
