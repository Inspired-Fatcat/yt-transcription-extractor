"""Main CourseBuilder service - orchestrates the entire pipeline."""

import json
from pathlib import Path
from typing import Optional, Callable

import re

from ..config import Config, load_config
from ..models import Chunk, Topic, Collection, CollectionType
from .database import CourseDatabase
from .vector_store import VectorStore
from ..processing.chunker import ChunkingService
from ..processing.embedder import EmbeddingService
from ..processing.topic_extractor import TopicExtractor
from ..processing.deduplicator import DeduplicationService


class CourseBuilderService:
    """
    Main orchestrator for course building operations.

    Handles the complete pipeline:
    1. Chunking transcripts
    2. Generating embeddings
    3. Topic extraction (Phase 2)
    4. Deduplication (Phase 2)
    5. Course generation (Phase 3)
    """

    def __init__(
        self,
        config: Optional[Config] = None,
        config_path: Optional[str] = None
    ):
        self.config = config or load_config(config_path)

        # Validate required API keys
        if not self.config.openai_api_key:
            raise ValueError("OpenAI API key required. Set OPENAI_API_KEY environment variable.")

        # Initialize services
        self.db = CourseDatabase(self.config.database_path)
        self.vector_store = VectorStore(
            persist_directory=self.config.vector_store.path,
            collection_name=self.config.vector_store.collection_name
        )
        self.chunker = ChunkingService(self.config.chunking)
        self.embedder = EmbeddingService(
            api_key=self.config.openai_api_key,
            config=self.config.embeddings,
            cache_dir=str(Path(self.config.vector_store.path) / "embedding_cache")
        )

        # Topic extractor (lazy initialization - needs Claude API key)
        self._topic_extractor = None

        # Deduplication service
        self.deduplicator = DeduplicationService(
            vector_store=self.vector_store,
            config=self.config.deduplication,
        )

        # Reference to existing transcript database
        self._transcript_db = None

    def _get_transcript_db(self):
        """Get connection to the existing transcript database."""
        if self._transcript_db is None:
            import sqlite3
            self._transcript_db = sqlite3.connect(self.config.database_path)
            self._transcript_db.row_factory = sqlite3.Row
        return self._transcript_db

    def _get_topic_extractor(self) -> TopicExtractor:
        """Get or create the topic extractor."""
        if self._topic_extractor is None:
            if not self.config.anthropic_api_key:
                raise ValueError("Anthropic API key required for topic extraction. Set ANTHROPIC_API_KEY.")
            self._topic_extractor = TopicExtractor(
                api_key=self.config.anthropic_api_key,
                config=self.config.llm,
            )
        return self._topic_extractor

    def get_all_videos(self) -> list[dict]:
        """Get all videos from the transcript database."""
        conn = self._get_transcript_db()
        cursor = conn.execute('''
            SELECT video_id, title, channel, duration
            FROM videos
            ORDER BY upload_date DESC
        ''')
        return [dict(row) for row in cursor.fetchall()]

    def get_transcript_segments(self, video_id: str) -> list[dict]:
        """Get transcript segments for a video."""
        conn = self._get_transcript_db()
        cursor = conn.execute(
            'SELECT segments_json FROM transcripts WHERE video_id = ?',
            (video_id,)
        )
        row = cursor.fetchone()
        if row and row['segments_json']:
            return json.loads(row['segments_json'])
        return []

    # ==================== PROCESSING PIPELINE ====================

    def process_video(
        self,
        video_id: str,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> dict:
        """
        Process a single video: chunk and embed.

        Args:
            video_id: YouTube video ID
            on_progress: Optional callback for progress updates

        Returns:
            Dict with processing results
        """
        result = {
            'video_id': video_id,
            'chunks_created': 0,
            'embeddings_created': 0,
            'error': None,
        }

        try:
            # Get transcript segments
            if on_progress:
                on_progress("Loading transcript...")

            segments = self.get_transcript_segments(video_id)
            if not segments:
                result['error'] = "No transcript found"
                return result

            # Chunk the transcript
            if on_progress:
                on_progress("Chunking transcript...")

            chunks = self.chunker.chunk_transcript(video_id, segments)
            result['chunks_created'] = len(chunks)

            if not chunks:
                result['error'] = "No chunks created (transcript too short?)"
                return result

            # Save chunks to database
            if on_progress:
                on_progress(f"Saving {len(chunks)} chunks...")

            chunk_ids = self.db.save_chunks(chunks)

            # Update chunk objects with IDs
            for chunk, chunk_id in zip(chunks, chunk_ids):
                chunk.id = chunk_id

            # Generate embeddings
            if on_progress:
                on_progress("Generating embeddings...")

            embeddings = self.embedder.embed_chunks(chunks)
            result['embeddings_created'] = len(embeddings)

            # Store in vector database
            if on_progress:
                on_progress("Storing in vector database...")

            # Get video metadata for context
            videos = self.get_all_videos()
            video_meta = next((v for v in videos if v['video_id'] == video_id), {})

            metadatas = []
            for chunk in chunks:
                metadatas.append({
                    'video_id': chunk.video_id,
                    'chunk_index': chunk.chunk_index,
                    'start_time': chunk.start_time,
                    'end_time': chunk.end_time,
                    'video_title': video_meta.get('title', ''),
                    'channel': video_meta.get('channel', ''),
                })

            self.vector_store.add_chunks(
                chunk_ids=chunk_ids,
                embeddings=embeddings,
                texts=[c.text for c in chunks],
                metadatas=metadatas
            )

            if on_progress:
                on_progress("Done!")

        except Exception as e:
            result['error'] = str(e)

        return result

    def process_all_videos(
        self,
        skip_processed: bool = True,
        on_progress: Optional[Callable[[int, int, str, str], None]] = None
    ) -> list[dict]:
        """
        Process all videos in the database.

        Args:
            skip_processed: Skip videos that already have chunks
            on_progress: Callback (current, total, video_id, status)

        Returns:
            List of processing results
        """
        videos = self.get_all_videos()
        results = []

        # Get already processed video IDs
        processed_ids = set()
        if skip_processed:
            all_chunks = self.db.get_all_chunks()
            processed_ids = {c.video_id for c in all_chunks}

        videos_to_process = [
            v for v in videos
            if v['video_id'] not in processed_ids
        ]

        total = len(videos_to_process)

        for i, video in enumerate(videos_to_process, 1):
            video_id = video['video_id']

            def progress_wrapper(status: str):
                if on_progress:
                    on_progress(i, total, video_id, status)

            result = self.process_video(video_id, on_progress=progress_wrapper)
            results.append(result)

        return results

    # ==================== TOPIC EXTRACTION ====================

    def extract_topics_from_chunk(
        self,
        chunk_id: int,
        on_progress: Optional[Callable[[str], None]] = None
    ) -> dict:
        """
        Extract topics from a single chunk.

        Returns:
            Dict with extraction results
        """
        chunk = self.db.get_chunk(chunk_id)
        if not chunk:
            return {'error': f"Chunk {chunk_id} not found"}

        # Get video metadata
        videos = self.get_all_videos()
        video_meta = next((v for v in videos if v['video_id'] == chunk.video_id), {})

        if on_progress:
            on_progress("Extracting topics...")

        extractor = self._get_topic_extractor()
        topics, main_theme, summary = extractor.extract_from_chunk(
            chunk=chunk,
            video_title=video_meta.get('title', 'Unknown'),
            channel=video_meta.get('channel', 'Unknown'),
        )

        # Save metadata
        self.db.save_chunk_metadata(chunk_id, main_theme, summary)

        # Save topics and link to chunk
        saved_topics = []
        for topic in topics:
            topic_id = self.db.save_topic(topic)
            relevance = topic.relevance_scores.get(chunk_id, 1.0)
            self.db.link_chunk_topic(chunk_id, topic_id, relevance)
            saved_topics.append({
                'id': topic_id,
                'name': topic.name,
                'category': topic.category.value,
            })

        if on_progress:
            on_progress(f"Extracted {len(topics)} topics")

        return {
            'chunk_id': chunk_id,
            'topics': saved_topics,
            'main_theme': main_theme,
            'summary': summary,
        }

    def extract_all_topics(
        self,
        skip_extracted: bool = True,
        collection_slug: Optional[str] = None,
        on_progress: Optional[Callable[[int, int, str, str], None]] = None
    ) -> list[dict]:
        """
        Extract topics from all chunks (or just those in a collection).

        Args:
            skip_extracted: Skip chunks that already have metadata
            collection_slug: Only process chunks from this collection
            on_progress: Callback (current, total, chunk_id, status)

        Returns:
            List of extraction results
        """
        # Get chunks to process
        if collection_slug:
            collection = self.db.get_collection(collection_slug)
            if not collection:
                return [{'error': f"Collection not found: {collection_slug}"}]
            chunks = self.db.get_chunks_for_collection(collection.id)
        else:
            chunks = self.db.get_all_chunks()

        # Filter already extracted if needed
        if skip_extracted:
            extracted_ids = set()
            for chunk in chunks:
                if self.db.get_chunk_metadata(chunk.id):
                    extracted_ids.add(chunk.id)
            chunks = [c for c in chunks if c.id not in extracted_ids]

        if not chunks:
            return []

        # Build video metadata lookup
        videos = self.get_all_videos()
        video_meta = {v['video_id']: v for v in videos}

        extractor = self._get_topic_extractor()
        results = []
        total = len(chunks)

        for i, chunk in enumerate(chunks, 1):
            if on_progress:
                on_progress(i, total, str(chunk.id), "Extracting topics...")

            try:
                meta = video_meta.get(chunk.video_id, {})
                topics, main_theme, summary = extractor.extract_from_chunk(
                    chunk=chunk,
                    video_title=meta.get('title', 'Unknown'),
                    channel=meta.get('channel', 'Unknown'),
                )

                # Save results
                self.db.save_chunk_metadata(chunk.id, main_theme, summary)

                saved_topics = []
                for topic in topics:
                    topic_id = self.db.save_topic(topic)
                    relevance = topic.relevance_scores.get(chunk.id, 1.0)
                    self.db.link_chunk_topic(chunk.id, topic_id, relevance)
                    saved_topics.append(topic.name)

                results.append({
                    'chunk_id': chunk.id,
                    'topics_count': len(saved_topics),
                    'main_theme': main_theme,
                    'error': None,
                })

                if on_progress:
                    on_progress(i, total, str(chunk.id), f"Extracted {len(saved_topics)} topics")

            except Exception as e:
                results.append({
                    'chunk_id': chunk.id,
                    'topics_count': 0,
                    'error': str(e),
                })
                if on_progress:
                    on_progress(i, total, str(chunk.id), f"Error: {e}")

        return results

    def get_all_topics(self) -> list[Topic]:
        """Get all topics ordered by mention count."""
        return self.db.get_all_topics()

    def get_topics_for_collection(self, slug: str) -> list[Topic]:
        """Get topics found in a specific collection's chunks."""
        collection = self.db.get_collection(slug)
        if not collection:
            return []

        # Get all chunks in collection
        chunks = self.db.get_chunks_for_collection(collection.id)
        chunk_ids = {c.id for c in chunks}

        # Get all topics and filter to those in collection chunks
        all_topics = self.db.get_all_topics()
        collection_topics = []

        for topic in all_topics:
            # Get chunks for this topic
            chunk_links = self.db.get_chunks_for_topic(topic.id)
            topic_chunk_ids = {c.id for c, _ in chunk_links}

            # If any of the topic's chunks are in this collection
            if topic_chunk_ids & chunk_ids:
                collection_topics.append(topic)

        return collection_topics

    # ==================== DEDUPLICATION ====================

    def find_duplicates(
        self,
        collection_slug: Optional[str] = None,
        threshold: Optional[float] = None,
        on_progress: Optional[Callable[[str], None]] = None,
    ) -> list[dict]:
        """
        Find duplicate content clusters.

        Args:
            collection_slug: Only find duplicates within this collection
            threshold: Similarity threshold (default from config)
            on_progress: Progress callback

        Returns:
            List of duplicate clusters with chunk info
        """
        if on_progress:
            on_progress("Finding similar pairs...")

        # Find similar pairs
        pairs = self.deduplicator.find_similar_pairs(threshold=threshold)

        if not pairs:
            return []

        # Filter to collection if specified
        if collection_slug:
            collection = self.db.get_collection(collection_slug)
            if not collection:
                return []
            collection_chunks = self.db.get_chunks_for_collection(collection.id)
            collection_chunk_ids = {c.id for c in collection_chunks}

            pairs = [
                (id1, id2, sim) for id1, id2, sim in pairs
                if id1 in collection_chunk_ids and id2 in collection_chunk_ids
            ]

        if on_progress:
            on_progress(f"Found {len(pairs)} similar pairs, clustering...")

        # Cluster into groups
        clusters = self.deduplicator.cluster_duplicates(pairs)

        if on_progress:
            on_progress(f"Found {len(clusters)} duplicate clusters")

        # Build video metadata lookup
        videos = self.get_all_videos()
        video_meta = {v['video_id']: v for v in videos}

        # Format results with chunk details
        results = []
        for cluster in clusters:
            cluster_info = {
                'size': len(cluster),
                'chunks': [],
            }

            for chunk_id, similarity in cluster:
                chunk = self.db.get_chunk(chunk_id)
                if chunk:
                    meta = video_meta.get(chunk.video_id, {})
                    cluster_info['chunks'].append({
                        'chunk_id': chunk_id,
                        'video_id': chunk.video_id,
                        'video_title': meta.get('title', 'Unknown'),
                        'timestamp': f"{int(chunk.start_time // 60)}:{int(chunk.start_time % 60):02d}",
                        'similarity': round(similarity, 3),
                        'text_preview': chunk.text[:150] + '...' if len(chunk.text) > 150 else chunk.text,
                    })

            if cluster_info['chunks']:
                results.append(cluster_info)

        return results

    def save_duplicate_groups(
        self,
        clusters: list[dict],
        on_progress: Optional[Callable[[int, int], None]] = None,
    ) -> int:
        """
        Save duplicate clusters to database.

        Returns:
            Number of groups saved
        """
        count = 0
        total = len(clusters)

        for i, cluster in enumerate(clusters):
            if on_progress:
                on_progress(i + 1, total)

            chunk_ids = [(c['chunk_id'], c['similarity']) for c in cluster['chunks']]
            group = self.deduplicator.create_duplicate_group(chunk_ids)
            self.db.save_duplicate_group(group)
            count += 1

        return count

    def get_duplicate_groups(self) -> list[dict]:
        """Get all saved duplicate groups with details."""
        groups = self.db.get_all_duplicate_groups()

        # Build video metadata lookup
        videos = self.get_all_videos()
        video_meta = {v['video_id']: v for v in videos}

        results = []
        for group in groups:
            group_info = {
                'id': group.id,
                'canonical_chunk_id': group.canonical_chunk_id,
                'merged_content': group.merged_content,
                'members': [],
            }

            for member in group.members:
                chunk = self.db.get_chunk(member.chunk_id)
                if chunk:
                    meta = video_meta.get(chunk.video_id, {})
                    group_info['members'].append({
                        'chunk_id': member.chunk_id,
                        'video_title': meta.get('title', 'Unknown'),
                        'timestamp': f"{int(chunk.start_time // 60)}:{int(chunk.start_time % 60):02d}",
                        'similarity': member.similarity_score,
                    })

            results.append(group_info)

        return results

    # ==================== SEARCH ====================

    def semantic_search(
        self,
        query: str,
        limit: int = 10
    ) -> list[dict]:
        """
        Search chunks by semantic similarity.

        Returns:
            List of dicts with chunk info and similarity scores
        """
        # Embed the query
        query_embedding = self.embedder.embed_text(query)

        # Search vector store
        results = self.vector_store.query(
            query_embedding,
            n_results=limit
        )

        search_results = []
        for i, (chunk_id, distance) in enumerate(zip(results['ids'], results['distances'])):
            similarity = 1 - distance
            metadata = results['metadatas'][i]
            text = results['documents'][i]

            search_results.append({
                'chunk_id': int(chunk_id),
                'similarity': round(similarity, 4),
                'video_id': metadata.get('video_id'),
                'video_title': metadata.get('video_title'),
                'channel': metadata.get('channel'),
                'timestamp': f"{int(metadata.get('start_time', 0) // 60)}:{int(metadata.get('start_time', 0) % 60):02d}",
                'text_preview': text[:200] + '...' if len(text) > 200 else text,
            })

        return search_results

    def find_similar_chunks(
        self,
        chunk_id: int,
        limit: int = 10,
        threshold: float = 0.7
    ) -> list[tuple[int, float]]:
        """Find chunks similar to a given chunk."""
        embedding = self.vector_store.get_embedding(chunk_id)
        if not embedding:
            return []

        similar = self.vector_store.query_similar(
            embedding,
            threshold=threshold,
            n_results=limit + 1  # +1 to exclude self
        )

        # Filter out the query chunk itself
        return [(cid, score) for cid, score in similar if cid != chunk_id][:limit]

    # ==================== COLLECTION OPERATIONS ====================

    def create_collection(
        self,
        name: str,
        description: str = "",
        collection_type: CollectionType = CollectionType.CUSTOM
    ) -> Collection:
        """Create a new collection (folder)."""
        # Generate slug from name
        slug = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')

        collection = Collection(
            name=name,
            slug=slug,
            description=description,
            collection_type=collection_type,
        )

        collection.id = self.db.create_collection(collection)
        return collection

    def get_collection(self, slug: str) -> Optional[Collection]:
        """Get a collection by slug."""
        return self.db.get_collection(slug)

    def list_collections(self) -> list[Collection]:
        """List all collections with stats."""
        return self.db.get_all_collections()

    def delete_collection(self, slug: str) -> bool:
        """Delete a collection."""
        collection = self.db.get_collection(slug)
        if not collection:
            return False
        self.db.delete_collection(collection.id)
        return True

    def add_video_to_collection(self, slug: str, video_id: str, notes: str = "") -> bool:
        """Add a video to a collection."""
        collection = self.db.get_collection(slug)
        if not collection:
            return False
        self.db.add_video_to_collection(collection.id, video_id, notes)
        return True

    def remove_video_from_collection(self, slug: str, video_id: str) -> bool:
        """Remove a video from a collection."""
        collection = self.db.get_collection(slug)
        if not collection:
            return False
        self.db.remove_video_from_collection(collection.id, video_id)
        return True

    def get_collection_videos(self, slug: str) -> list[dict]:
        """Get all videos in a collection with metadata."""
        collection = self.db.get_collection(slug)
        if not collection:
            return []

        video_ids = self.db.get_collection_videos(collection.id)
        all_videos = self.get_all_videos()

        return [v for v in all_videos if v['video_id'] in video_ids]

    def search_in_collection(
        self,
        slug: str,
        query: str,
        limit: int = 10
    ) -> list[dict]:
        """Search only within a specific collection."""
        collection = self.db.get_collection(slug)
        if not collection:
            return []

        video_ids = self.db.get_collection_videos(collection.id)
        if not video_ids:
            return []

        # Embed the query
        query_embedding = self.embedder.embed_text(query)

        # Search with video filter
        results = self.vector_store.query(
            query_embedding,
            n_results=limit,
            video_ids=video_ids
        )

        search_results = []
        for i, (chunk_id, distance) in enumerate(zip(results['ids'], results['distances'])):
            similarity = 1 - distance
            metadata = results['metadatas'][i]
            text = results['documents'][i]

            search_results.append({
                'chunk_id': int(chunk_id),
                'similarity': round(similarity, 4),
                'video_id': metadata.get('video_id'),
                'video_title': metadata.get('video_title'),
                'channel': metadata.get('channel'),
                'timestamp': f"{int(metadata.get('start_time', 0) // 60)}:{int(metadata.get('start_time', 0) % 60):02d}",
                'text_preview': text[:200] + '...' if len(text) > 200 else text,
            })

        return search_results

    def get_collection_stats(self, slug: str) -> Optional[dict]:
        """Get statistics for a specific collection."""
        collection = self.db.get_collection(slug)
        if not collection:
            return None
        return self.db.get_collection_stats(collection.id)

    # ==================== STATS ====================

    def get_stats(self) -> dict:
        """Get comprehensive statistics."""
        db_stats = self.db.get_stats()
        vector_count = self.vector_store.count()

        # Get video stats from transcript DB
        videos = self.get_all_videos()

        return {
            **db_stats,
            'video_count': len(videos),
            'embedding_count': vector_count,
            'embeddings_synced': vector_count == db_stats['chunk_count'],
        }

    def close(self):
        """Close all connections."""
        self.db.close()
        if self._transcript_db:
            self._transcript_db.close()
