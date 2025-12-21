"""Embedding service using OpenAI API."""

import hashlib
import json
from pathlib import Path
from typing import Optional

from openai import OpenAI

from ..models import Chunk
from ..config import EmbeddingConfig


class EmbeddingService:
    """Generate embeddings using OpenAI API."""

    def __init__(
        self,
        api_key: str,
        config: Optional[EmbeddingConfig] = None,
        cache_dir: Optional[str] = None
    ):
        self.client = OpenAI(api_key=api_key)
        self.config = config or EmbeddingConfig()
        self.cache_dir = Path(cache_dir) if cache_dir else None

        if self.cache_dir and self.config.cache_embeddings:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def embed_text(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        # Check cache first
        if self.config.cache_embeddings and self.cache_dir:
            cached = self._get_cached(text)
            if cached is not None:
                return cached

        response = self.client.embeddings.create(
            model=self.config.model,
            input=text,
        )

        embedding = response.data[0].embedding

        # Cache the result
        if self.config.cache_embeddings and self.cache_dir:
            self._cache_embedding(text, embedding)

        return embedding

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts with batching."""
        if not texts:
            return []

        embeddings = [None] * len(texts)
        texts_to_embed = []
        indices_to_embed = []

        # Check cache for each text
        if self.config.cache_embeddings and self.cache_dir:
            for i, text in enumerate(texts):
                cached = self._get_cached(text)
                if cached is not None:
                    embeddings[i] = cached
                else:
                    texts_to_embed.append(text)
                    indices_to_embed.append(i)
        else:
            texts_to_embed = texts
            indices_to_embed = list(range(len(texts)))

        # Embed remaining texts in batches
        for batch_start in range(0, len(texts_to_embed), self.config.batch_size):
            batch_end = min(batch_start + self.config.batch_size, len(texts_to_embed))
            batch_texts = texts_to_embed[batch_start:batch_end]
            batch_indices = indices_to_embed[batch_start:batch_end]

            response = self.client.embeddings.create(
                model=self.config.model,
                input=batch_texts,
            )

            for j, item in enumerate(response.data):
                idx = batch_indices[j]
                embeddings[idx] = item.embedding

                # Cache the result
                if self.config.cache_embeddings and self.cache_dir:
                    self._cache_embedding(batch_texts[j], item.embedding)

        return embeddings

    def embed_chunk(self, chunk: Chunk) -> list[float]:
        """Generate embedding for a chunk."""
        return self.embed_text(chunk.text)

    def embed_chunks(self, chunks: list[Chunk]) -> list[list[float]]:
        """Generate embeddings for multiple chunks."""
        texts = [chunk.text for chunk in chunks]
        return self.embed_texts(texts)

    def _get_cache_key(self, text: str) -> str:
        """Generate cache key for a text."""
        # Include model in hash to invalidate cache on model change
        content = f"{self.config.model}:{text}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _get_cached(self, text: str) -> Optional[list[float]]:
        """Get cached embedding for a text."""
        if not self.cache_dir:
            return None

        cache_key = self._get_cache_key(text)
        cache_file = self.cache_dir / f"{cache_key}.json"

        if cache_file.exists():
            with open(cache_file) as f:
                return json.load(f)
        return None

    def _cache_embedding(self, text: str, embedding: list[float]):
        """Cache an embedding."""
        if not self.cache_dir:
            return

        cache_key = self._get_cache_key(text)
        cache_file = self.cache_dir / f"{cache_key}.json"

        with open(cache_file, 'w') as f:
            json.dump(embedding, f)

    def clear_cache(self):
        """Clear the embedding cache."""
        if self.cache_dir and self.cache_dir.exists():
            for f in self.cache_dir.glob("*.json"):
                f.unlink()
