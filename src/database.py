"""SQLite database for storing video metadata and transcripts."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Generator

from .video_info import VideoMetadata
from .transcript import Transcript
from .exceptions import (
    DatabaseConnectionError,
    DatabaseIntegrityError,
    TransactionError,
)
from .logging_config import get_logger

logger = get_logger('database')


class TranscriptDatabase:
    """SQLite database for YouTube video data.

    Supports context manager protocol for automatic cleanup:
        with TranscriptDatabase('data/transcripts.db') as db:
            db.save_video(metadata)
    """

    def __init__(self, db_path: str = "data/transcripts.db"):
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self._init_db()

    def _init_db(self):
        """Initialize database and create tables."""
        try:
            # Ensure parent directory exists
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row

            # Enable foreign key constraints
            self.conn.execute("PRAGMA foreign_keys = ON")

            logger.debug(f"Connected to database: {self.db_path}")

            self.conn.executescript('''
                CREATE TABLE IF NOT EXISTS videos (
                    video_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    channel TEXT,
                    channel_id TEXT,
                    upload_date TEXT,
                    duration INTEGER,
                    description TEXT,
                    view_count INTEGER,
                    like_count INTEGER,
                    thumbnail_url TEXT,
                    tags TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS transcripts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL,
                    language TEXT NOT NULL,
                    is_generated BOOLEAN,
                    full_text TEXT,
                    segments_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
                    UNIQUE(video_id, language)
                );

                CREATE INDEX IF NOT EXISTS idx_videos_channel ON videos(channel_id);
                CREATE INDEX IF NOT EXISTS idx_videos_upload_date ON videos(upload_date);
                CREATE INDEX IF NOT EXISTS idx_transcripts_video ON transcripts(video_id);
                CREATE INDEX IF NOT EXISTS idx_transcripts_language ON transcripts(language);

                CREATE VIRTUAL TABLE IF NOT EXISTS transcript_fts USING fts5(
                    video_id,
                    full_text,
                    content='transcripts',
                    content_rowid='id'
                );

                CREATE TRIGGER IF NOT EXISTS transcripts_ai AFTER INSERT ON transcripts BEGIN
                    INSERT INTO transcript_fts(rowid, video_id, full_text)
                    VALUES (new.id, new.video_id, new.full_text);
                END;

                CREATE TRIGGER IF NOT EXISTS transcripts_ad AFTER DELETE ON transcripts BEGIN
                    INSERT INTO transcript_fts(transcript_fts, rowid, video_id, full_text)
                    VALUES('delete', old.id, old.video_id, old.full_text);
                END;

                CREATE TRIGGER IF NOT EXISTS transcripts_au AFTER UPDATE ON transcripts BEGIN
                    INSERT INTO transcript_fts(transcript_fts, rowid, video_id, full_text)
                    VALUES('delete', old.id, old.video_id, old.full_text);
                    INSERT INTO transcript_fts(rowid, video_id, full_text)
                    VALUES (new.id, new.video_id, new.full_text);
                END;
            ''')
            self.conn.commit()
            logger.debug("Database schema initialized")

        except sqlite3.Error as e:
            logger.error(f"Failed to initialize database: {e}")
            raise DatabaseConnectionError(str(self.db_path), reason=str(e))

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - ensures database is closed."""
        self.close()
        return False

    @contextmanager
    def transaction(self) -> Generator[None, None, None]:
        """Context manager for database transactions.

        Automatically commits on success, rolls back on exception.

        Usage:
            with db.transaction():
                db.save_video(metadata)
                db.save_transcript(transcript)
        """
        try:
            yield
            self.conn.commit()
            logger.debug("Transaction committed")
        except sqlite3.IntegrityError as e:
            self.conn.rollback()
            logger.error(f"Transaction rolled back (integrity error): {e}")
            raise DatabaseIntegrityError(str(e))
        except Exception as e:
            self.conn.rollback()
            logger.error(f"Transaction rolled back: {e}")
            raise TransactionError("transaction", reason=str(e))

    def save_video(self, metadata: VideoMetadata) -> None:
        """Save or update video metadata."""
        logger.debug(f"Saving video: {metadata.video_id}")
        try:
            self.conn.execute('''
                INSERT INTO videos (
                    video_id, title, channel, channel_id, upload_date,
                    duration, description, view_count, like_count,
                    thumbnail_url, tags, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(video_id) DO UPDATE SET
                    title=excluded.title,
                    channel=excluded.channel,
                    channel_id=excluded.channel_id,
                    upload_date=excluded.upload_date,
                    duration=excluded.duration,
                    description=excluded.description,
                    view_count=excluded.view_count,
                    like_count=excluded.like_count,
                    thumbnail_url=excluded.thumbnail_url,
                    tags=excluded.tags,
                    updated_at=CURRENT_TIMESTAMP
            ''', (
                metadata.video_id,
                metadata.title,
                metadata.channel,
                metadata.channel_id,
                metadata.upload_date,
                metadata.duration,
                metadata.description,
                metadata.view_count,
                metadata.like_count,
                metadata.thumbnail_url,
                json.dumps(metadata.tags),
            ))
            self.conn.commit()
        except sqlite3.IntegrityError as e:
            logger.error(f"Integrity error saving video {metadata.video_id}: {e}")
            raise DatabaseIntegrityError(f"Failed to save video: {e}")

    def save_transcript(self, transcript: Transcript) -> None:
        """Save or update a transcript."""
        logger.debug(f"Saving transcript for video: {transcript.video_id}")
        segments_json = json.dumps([
            {'text': s.text, 'start': s.start, 'duration': s.duration}
            for s in transcript.segments
        ])

        try:
            self.conn.execute('''
                INSERT INTO transcripts (
                    video_id, language, is_generated, full_text, segments_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(video_id, language) DO UPDATE SET
                    is_generated=excluded.is_generated,
                    full_text=excluded.full_text,
                    segments_json=excluded.segments_json
            ''', (
                transcript.video_id,
                transcript.language,
                transcript.is_generated,
                transcript.full_text,
                segments_json,
            ))
            self.conn.commit()
        except sqlite3.IntegrityError as e:
            logger.error(f"Integrity error saving transcript for {transcript.video_id}: {e}")
            raise DatabaseIntegrityError(f"Failed to save transcript: {e}")

    def save_video_with_transcript(
        self,
        metadata: VideoMetadata,
        transcript: Optional[Transcript] = None
    ) -> None:
        """Atomically save video metadata and transcript together.

        If either operation fails, both are rolled back.
        """
        logger.debug(f"Saving video with transcript: {metadata.video_id}")
        with self.transaction():
            # Save video (without committing)
            self.conn.execute('''
                INSERT INTO videos (
                    video_id, title, channel, channel_id, upload_date,
                    duration, description, view_count, like_count,
                    thumbnail_url, tags, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(video_id) DO UPDATE SET
                    title=excluded.title,
                    channel=excluded.channel,
                    channel_id=excluded.channel_id,
                    upload_date=excluded.upload_date,
                    duration=excluded.duration,
                    description=excluded.description,
                    view_count=excluded.view_count,
                    like_count=excluded.like_count,
                    thumbnail_url=excluded.thumbnail_url,
                    tags=excluded.tags,
                    updated_at=CURRENT_TIMESTAMP
            ''', (
                metadata.video_id,
                metadata.title,
                metadata.channel,
                metadata.channel_id,
                metadata.upload_date,
                metadata.duration,
                metadata.description,
                metadata.view_count,
                metadata.like_count,
                metadata.thumbnail_url,
                json.dumps(metadata.tags),
            ))

            # Save transcript if provided
            if transcript:
                segments_json = json.dumps([
                    {'text': s.text, 'start': s.start, 'duration': s.duration}
                    for s in transcript.segments
                ])
                self.conn.execute('''
                    INSERT INTO transcripts (
                        video_id, language, is_generated, full_text, segments_json
                    ) VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(video_id, language) DO UPDATE SET
                        is_generated=excluded.is_generated,
                        full_text=excluded.full_text,
                        segments_json=excluded.segments_json
                ''', (
                    transcript.video_id,
                    transcript.language,
                    transcript.is_generated,
                    transcript.full_text,
                    segments_json,
                ))

    def get_video(self, video_id: str) -> Optional[dict]:
        """Get video metadata by ID."""
        cursor = self.conn.execute(
            'SELECT * FROM videos WHERE video_id = ?', (video_id,)
        )
        row = cursor.fetchone()
        if row:
            result = dict(row)
            result['tags'] = json.loads(result['tags']) if result['tags'] else []
            return result
        return None

    def get_transcript(self, video_id: str, language: str = 'en') -> Optional[dict]:
        """Get transcript for a video."""
        cursor = self.conn.execute(
            'SELECT * FROM transcripts WHERE video_id = ? AND language = ?',
            (video_id, language)
        )
        row = cursor.fetchone()
        if row:
            result = dict(row)
            result['segments'] = json.loads(result['segments_json']) if result['segments_json'] else []
            return result
        return None

    def video_exists(self, video_id: str) -> bool:
        """Check if a video is already in the database."""
        cursor = self.conn.execute(
            'SELECT 1 FROM videos WHERE video_id = ?', (video_id,)
        )
        return cursor.fetchone() is not None

    def search_transcripts(self, query: str, limit: int = 20) -> list[dict]:
        """Full-text search across transcripts."""
        logger.debug(f"Searching for: '{query}' (limit={limit})")
        cursor = self.conn.execute('''
            SELECT v.video_id, v.title, v.channel, v.thumbnail_url,
                   snippet(transcript_fts, 1, '<mark>', '</mark>', '...', 64) as snippet
            FROM transcript_fts
            JOIN videos v ON transcript_fts.video_id = v.video_id
            WHERE transcript_fts MATCH ?
            ORDER BY rank
            LIMIT ?
        ''', (query, limit))
        results = [dict(row) for row in cursor.fetchall()]
        logger.debug(f"Found {len(results)} results")
        return results

    def get_all_videos(self, limit: int = 100, offset: int = 0) -> list[dict]:
        """Get all videos with pagination."""
        cursor = self.conn.execute('''
            SELECT v.*,
                   (SELECT COUNT(*) FROM transcripts t WHERE t.video_id = v.video_id) as transcript_count
            FROM videos v
            ORDER BY v.upload_date DESC
            LIMIT ? OFFSET ?
        ''', (limit, offset))
        results = []
        for row in cursor.fetchall():
            result = dict(row)
            result['tags'] = json.loads(result['tags']) if result['tags'] else []
            results.append(result)
        return results

    def get_stats(self) -> dict:
        """Get database statistics."""
        video_count = self.conn.execute('SELECT COUNT(*) FROM videos').fetchone()[0]
        transcript_count = self.conn.execute('SELECT COUNT(*) FROM transcripts').fetchone()[0]
        channels = self.conn.execute('SELECT COUNT(DISTINCT channel_id) FROM videos').fetchone()[0]
        total_duration = self.conn.execute('SELECT SUM(duration) FROM videos').fetchone()[0] or 0

        return {
            'video_count': video_count,
            'transcript_count': transcript_count,
            'unique_channels': channels,
            'total_duration_hours': round(total_duration / 3600, 2),
        }

    # ==========================================================================
    # CRUD Operations
    # ==========================================================================

    def update_video(self, video_id: str, **fields) -> bool:
        """Update specific fields of a video.

        Args:
            video_id: Video ID to update
            **fields: Fields to update (e.g., title='New Title', duration=120)

        Returns:
            True if video was updated, False if not found
        """
        if not fields:
            return False

        valid_fields = {
            'title', 'channel', 'channel_id', 'upload_date', 'duration',
            'description', 'view_count', 'like_count', 'thumbnail_url', 'tags'
        }

        # Filter to only valid fields
        updates = {k: v for k, v in fields.items() if k in valid_fields}
        if not updates:
            return False

        # Handle tags specially (convert to JSON)
        if 'tags' in updates:
            updates['tags'] = json.dumps(updates['tags'])

        set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
        values = list(updates.values()) + [video_id]

        cursor = self.conn.execute(
            f'UPDATE videos SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE video_id = ?',
            values
        )
        self.conn.commit()

        updated = cursor.rowcount > 0
        if updated:
            logger.debug(f"Updated video {video_id}: {list(updates.keys())}")
        return updated

    def delete_video(self, video_id: str, cascade: bool = True) -> bool:
        """Delete a video and optionally its transcripts.

        Args:
            video_id: Video ID to delete
            cascade: If True, delete associated transcripts (default due to FK)

        Returns:
            True if video was deleted, False if not found
        """
        logger.debug(f"Deleting video: {video_id} (cascade={cascade})")

        with self.transaction():
            if cascade:
                # Transcripts will be deleted by ON DELETE CASCADE
                pass
            else:
                # Check if there are transcripts
                cursor = self.conn.execute(
                    'SELECT COUNT(*) FROM transcripts WHERE video_id = ?',
                    (video_id,)
                )
                if cursor.fetchone()[0] > 0:
                    raise DatabaseIntegrityError(
                        f"Cannot delete video {video_id}: has transcripts and cascade=False"
                    )

            cursor = self.conn.execute(
                'DELETE FROM videos WHERE video_id = ?',
                (video_id,)
            )

        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Deleted video: {video_id}")
        return deleted

    def delete_transcript(self, video_id: str, language: str = 'en') -> bool:
        """Delete a specific transcript.

        Args:
            video_id: Video ID
            language: Language code of transcript to delete

        Returns:
            True if transcript was deleted, False if not found
        """
        cursor = self.conn.execute(
            'DELETE FROM transcripts WHERE video_id = ? AND language = ?',
            (video_id, language)
        )
        self.conn.commit()

        deleted = cursor.rowcount > 0
        if deleted:
            logger.debug(f"Deleted transcript for {video_id} ({language})")
        return deleted

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.debug("Database connection closed")
