"""ChromaDB vector store for semantic search."""

import hashlib
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

from ..models import Chunk


class VectorStore:
    """ChromaDB wrapper for chunk embeddings."""

    def __init__(
        self,
        persist_directory: str = "chroma_data",
        collection_name: str = "transcript_chunks"
    ):
        self.persist_directory = Path(persist_directory)
        self.collection_name = collection_name

        # Initialize ChromaDB with persistence
        self.client = chromadb.PersistentClient(
            path=str(self.persist_directory),
            settings=Settings(anonymized_telemetry=False)
        )

        # Get or create the collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def add_chunk(
        self,
        chunk_id: int,
        embedding: list[float],
        text: str,
        metadata: Optional[dict] = None
    ):
        """Add a single chunk embedding to the store."""
        meta = metadata or {}
        meta['chunk_id'] = chunk_id

        self.collection.add(
            ids=[str(chunk_id)],
            embeddings=[embedding],
            documents=[text],
            metadatas=[meta]
        )

    def add_chunks(
        self,
        chunk_ids: list[int],
        embeddings: list[list[float]],
        texts: list[str],
        metadatas: Optional[list[dict]] = None
    ):
        """Add multiple chunk embeddings to the store."""
        if not chunk_ids:
            return

        ids = [str(cid) for cid in chunk_ids]
        metas = metadatas or [{} for _ in chunk_ids]

        # Add chunk_id to each metadata
        for i, meta in enumerate(metas):
            meta['chunk_id'] = chunk_ids[i]

        self.collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metas
        )

    def query(
        self,
        query_embedding: list[float],
        n_results: int = 10,
        where: Optional[dict] = None,
        video_ids: Optional[list[str]] = None,
        include_distances: bool = True
    ) -> dict:
        """
        Query for similar chunks.

        Args:
            query_embedding: The embedding to search for
            n_results: Maximum number of results
            where: ChromaDB filter dict
            video_ids: Optional list of video IDs to filter by (for collection search)
            include_distances: Include distance scores

        Returns:
            Dict with 'ids', 'documents', 'metadatas', 'distances'
        """
        include = ["documents", "metadatas"]
        if include_distances:
            include.append("distances")

        # Build filter for video_ids if provided
        query_where = where
        if video_ids:
            video_filter = {"video_id": {"$in": video_ids}}
            if query_where:
                query_where = {"$and": [query_where, video_filter]}
            else:
                query_where = video_filter

        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where=query_where,
            include=include
        )

        # Flatten results (query returns nested lists)
        return {
            'ids': results['ids'][0] if results['ids'] else [],
            'documents': results['documents'][0] if results['documents'] else [],
            'metadatas': results['metadatas'][0] if results['metadatas'] else [],
            'distances': results['distances'][0] if results.get('distances') else [],
        }

    def query_similar(
        self,
        query_embedding: list[float],
        threshold: float = 0.85,
        n_results: int = 50
    ) -> list[tuple[int, float]]:
        """
        Find chunks similar to the query embedding above a threshold.

        Returns:
            List of (chunk_id, similarity_score) tuples
        """
        results = self.query(query_embedding, n_results=n_results)

        similar = []
        for i, distance in enumerate(results['distances']):
            # ChromaDB returns cosine distance, convert to similarity
            similarity = 1 - distance
            if similarity >= threshold:
                chunk_id = int(results['ids'][i])
                similar.append((chunk_id, similarity))

        return similar

    def find_all_similar_pairs(
        self,
        threshold: float = 0.85,
        batch_size: int = 100
    ) -> list[tuple[int, int, float]]:
        """
        Find all pairs of similar chunks above threshold.

        Returns:
            List of (chunk_id_1, chunk_id_2, similarity) tuples
        """
        # Get all embeddings
        all_data = self.collection.get(include=['embeddings', 'metadatas'])

        if not all_data['ids']:
            return []

        pairs = []
        seen = set()

        for i, (id1, emb) in enumerate(zip(all_data['ids'], all_data['embeddings'])):
            # Query for similar chunks
            results = self.query(emb, n_results=batch_size)

            for j, (id2, distance) in enumerate(zip(results['ids'], results['distances'])):
                if id1 == id2:
                    continue

                similarity = 1 - distance
                if similarity < threshold:
                    continue

                # Create canonical pair (smaller id first)
                pair_key = tuple(sorted([int(id1), int(id2)]))
                if pair_key in seen:
                    continue

                seen.add(pair_key)
                pairs.append((int(id1), int(id2), similarity))

        return pairs

    def get_embedding(self, chunk_id: int) -> Optional[list[float]]:
        """Get the embedding for a specific chunk."""
        result = self.collection.get(
            ids=[str(chunk_id)],
            include=['embeddings']
        )
        if result['embeddings']:
            return result['embeddings'][0]
        return None

    def get_all_chunk_ids(self) -> set[int]:
        """Get all chunk IDs that have embeddings."""
        result = self.collection.get(include=[])
        return {int(id) for id in result['ids']}

    def delete_chunk(self, chunk_id: int):
        """Delete a chunk embedding."""
        self.collection.delete(ids=[str(chunk_id)])

    def delete_chunks(self, chunk_ids: list[int]):
        """Delete multiple chunk embeddings."""
        if chunk_ids:
            self.collection.delete(ids=[str(cid) for cid in chunk_ids])

    def count(self) -> int:
        """Get the number of embeddings in the collection."""
        return self.collection.count()

    def clear(self):
        """Clear all embeddings from the collection."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )


class TopicVectorStore(VectorStore):
    """Vector store specifically for topic embeddings."""

    def __init__(self, persist_directory: str = "chroma_data"):
        super().__init__(
            persist_directory=persist_directory,
            collection_name="topics"
        )

    def add_topic(
        self,
        topic_id: int,
        embedding: list[float],
        name: str,
        description: str,
        category: str
    ):
        """Add a topic embedding."""
        self.collection.add(
            ids=[str(topic_id)],
            embeddings=[embedding],
            documents=[f"{name}: {description}"],
            metadatas=[{
                'topic_id': topic_id,
                'name': name,
                'category': category,
            }]
        )

    def find_similar_topics(
        self,
        query_embedding: list[float],
        n_results: int = 5,
        threshold: float = 0.7
    ) -> list[tuple[int, str, float]]:
        """
        Find topics similar to a query.

        Returns:
            List of (topic_id, topic_name, similarity) tuples
        """
        results = self.query(query_embedding, n_results=n_results)

        similar = []
        for i, distance in enumerate(results['distances']):
            similarity = 1 - distance
            if similarity >= threshold:
                topic_id = results['metadatas'][i]['topic_id']
                topic_name = results['metadatas'][i]['name']
                similar.append((topic_id, topic_name, similarity))

        return similar
