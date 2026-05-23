from __future__ import annotations

from typing import Any

from ceo_talk_monitor.config import VectorStoreConfig, get_settings
from ceo_talk_monitor.embeddings import Embedder


class VectorStore:
    def __init__(self, config: VectorStoreConfig):
        self.config = config
        self.embedder = Embedder(config.embedding_model)
        self._client = None

    @property
    def client(self):
        if self._client is None:
            from qdrant_client import QdrantClient

            settings = get_settings()
            self._client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key,
                check_compatibility=False,
            )
        return self._client

    def ensure_collection(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        collections = self.client.get_collections().collections
        names = {collection.name for collection in collections}
        if self.config.collection_name in names:
            return
        self.client.create_collection(
            collection_name=self.config.collection_name,
            vectors_config=VectorParams(size=self.embedder.size, distance=Distance.COSINE),
        )

    def upsert_talk(self, talk_id: int, text: str, payload: dict[str, Any]) -> None:
        from qdrant_client.models import PointStruct

        if not text.strip():
            return
        self.ensure_collection()
        self.client.upsert(
            collection_name=self.config.collection_name,
            points=[PointStruct(id=talk_id, vector=self.embedder.embed(text), payload=payload)],
        )

    def search(self, query: str, limit: int = 10) -> list[dict[str, Any]]:
        self.ensure_collection()
        vector = self.embedder.embed(query)
        try:
            points = self.client.query_points(
                collection_name=self.config.collection_name,
                query=vector,
                limit=limit,
                with_payload=True,
            ).points
        except AttributeError:
            points = self.client.search(
                collection_name=self.config.collection_name,
                query_vector=vector,
                limit=limit,
                with_payload=True,
            )
        return [
            {
                "id": point.id,
                "score": float(point.score),
                "payload": point.payload or {},
            }
            for point in points
        ]
