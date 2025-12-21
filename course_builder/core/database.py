"""Extended database operations for Course Builder."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional, Generator

from ..models import (
    Chunk, Topic, TopicCategory, ChunkTopic,
    Course, Module, Lesson, LessonSource,
    DuplicateGroup, DuplicateGroupMember,
    DifficultyLevel, CourseStatus, SourceUsageType,
    Collection, CollectionType, CollectionVideo,
)

# Import shared logging and exceptions
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from src.logging_config import get_logger
from src.exceptions import (
    DatabaseConnectionError,
    DatabaseIntegrityError,
    TransactionError,
)

logger = get_logger('course_builder.database')


class CourseDatabase:
    """SQLite database for course builder data.

    Supports context manager protocol for automatic cleanup:
        with CourseDatabase('data/transcripts.db') as db:
            db.create_collection(collection)
    """

    def __init__(self, db_path: str = "data/transcripts.db"):
        self.db_path = Path(db_path)
        self.conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._init_tables()

    def _connect(self):
        """Establish database connection."""
        try:
            self.conn = sqlite3.connect(self.db_path)
            self.conn.row_factory = sqlite3.Row
            # Enable foreign key constraints
            self.conn.execute("PRAGMA foreign_keys = ON")
            logger.debug(f"Connected to database: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Failed to connect to database: {e}")
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
                db.save_chunk(chunk)
                db.link_chunk_topic(chunk_id, topic_id)
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

    def _init_tables(self):
        """Create course builder tables if they don't exist."""
        logger.debug("Initializing course builder tables")
        self.conn.executescript('''
            -- Semantic chunks of transcripts
            CREATE TABLE IF NOT EXISTS chunks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                chunk_index INTEGER NOT NULL,
                text TEXT NOT NULL,
                start_time REAL NOT NULL,
                end_time REAL NOT NULL,
                token_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE,
                UNIQUE(video_id, chunk_index)
            );

            -- Extracted concepts/techniques
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT,
                category TEXT DEFAULT 'concept',
                parent_topic_id INTEGER,
                confidence REAL DEFAULT 1.0,
                mention_count INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (parent_topic_id) REFERENCES topics(id)
            );

            -- Many-to-many chunk-topic associations
            CREATE TABLE IF NOT EXISTS chunk_topics (
                chunk_id INTEGER NOT NULL,
                topic_id INTEGER NOT NULL,
                relevance_score REAL DEFAULT 1.0,
                PRIMARY KEY (chunk_id, topic_id),
                FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE,
                FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
            );

            -- Duplicate content clusters
            CREATE TABLE IF NOT EXISTS duplicate_groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_hash TEXT UNIQUE,
                canonical_chunk_id INTEGER,
                merged_content TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (canonical_chunk_id) REFERENCES chunks(id)
            );

            -- Duplicate group members
            CREATE TABLE IF NOT EXISTS duplicate_group_members (
                group_id INTEGER NOT NULL,
                chunk_id INTEGER NOT NULL,
                similarity_score REAL NOT NULL,
                PRIMARY KEY (group_id, chunk_id),
                FOREIGN KEY (group_id) REFERENCES duplicate_groups(id) ON DELETE CASCADE,
                FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
            );

            -- Course structure
            CREATE TABLE IF NOT EXISTS courses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                target_audience TEXT,
                difficulty_level TEXT DEFAULT 'intermediate',
                status TEXT DEFAULT 'draft',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Modules within a course
            CREATE TABLE IF NOT EXISTS modules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                sequence_order INTEGER NOT NULL,
                learning_objectives TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (course_id) REFERENCES courses(id) ON DELETE CASCADE
            );

            -- Lessons within modules
            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                module_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                sequence_order INTEGER NOT NULL,
                content TEXT,
                summary TEXT,
                key_takeaways TEXT,
                estimated_duration INTEGER DEFAULT 0,
                difficulty_level TEXT DEFAULT 'intermediate',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (module_id) REFERENCES modules(id) ON DELETE CASCADE
            );

            -- Source references for lessons
            CREATE TABLE IF NOT EXISTS lesson_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER NOT NULL,
                chunk_id INTEGER NOT NULL,
                usage_type TEXT DEFAULT 'primary',
                relevance_score REAL DEFAULT 1.0,
                quote TEXT,
                FOREIGN KEY (lesson_id) REFERENCES lessons(id) ON DELETE CASCADE,
                FOREIGN KEY (chunk_id) REFERENCES chunks(id)
            );

            -- Processing jobs for tracking pipeline state
            CREATE TABLE IF NOT EXISTS processing_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_type TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                video_id TEXT,
                parameters TEXT,
                result TEXT,
                error_message TEXT,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Collections (folders for organizing content)
            CREATE TABLE IF NOT EXISTS collections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                description TEXT,
                collection_type TEXT DEFAULT 'custom',
                config TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            -- Collection-Video associations
            CREATE TABLE IF NOT EXISTS collection_videos (
                collection_id INTEGER NOT NULL,
                video_id TEXT NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                PRIMARY KEY (collection_id, video_id),
                FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
                FOREIGN KEY (video_id) REFERENCES videos(video_id) ON DELETE CASCADE
            );

            -- Collection-specific topics (topics can belong to multiple collections)
            CREATE TABLE IF NOT EXISTS collection_topics (
                collection_id INTEGER NOT NULL,
                topic_id INTEGER NOT NULL,
                PRIMARY KEY (collection_id, topic_id),
                FOREIGN KEY (collection_id) REFERENCES collections(id) ON DELETE CASCADE,
                FOREIGN KEY (topic_id) REFERENCES topics(id) ON DELETE CASCADE
            );

            -- Chunk metadata (extracted by LLM)
            CREATE TABLE IF NOT EXISTS chunk_metadata (
                chunk_id INTEGER PRIMARY KEY,
                main_theme TEXT,
                summary TEXT,
                extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chunk_id) REFERENCES chunks(id) ON DELETE CASCADE
            );

            -- Indexes for performance
            CREATE INDEX IF NOT EXISTS idx_chunks_video ON chunks(video_id);
            CREATE INDEX IF NOT EXISTS idx_chunk_topics_topic ON chunk_topics(topic_id);
            CREATE INDEX IF NOT EXISTS idx_chunk_topics_chunk ON chunk_topics(chunk_id);
            CREATE INDEX IF NOT EXISTS idx_lessons_module ON lessons(module_id);
            CREATE INDEX IF NOT EXISTS idx_modules_course ON modules(course_id);
            CREATE INDEX IF NOT EXISTS idx_processing_jobs_status ON processing_jobs(status, job_type);
            CREATE INDEX IF NOT EXISTS idx_duplicate_members_chunk ON duplicate_group_members(chunk_id);
            CREATE INDEX IF NOT EXISTS idx_collection_videos_video ON collection_videos(video_id);
            CREATE INDEX IF NOT EXISTS idx_collections_slug ON collections(slug);
        ''')
        self.conn.commit()

    # ==================== CHUNK OPERATIONS ====================

    def save_chunk(self, chunk: Chunk) -> int:
        """Save a chunk and return its ID."""
        logger.debug(f"Saving chunk: video={chunk.video_id}, index={chunk.chunk_index}")
        cursor = self.conn.execute('''
            INSERT INTO chunks (video_id, chunk_index, text, start_time, end_time, token_count)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id, chunk_index) DO UPDATE SET
                text=excluded.text,
                start_time=excluded.start_time,
                end_time=excluded.end_time,
                token_count=excluded.token_count
        ''', (chunk.video_id, chunk.chunk_index, chunk.text,
              chunk.start_time, chunk.end_time, chunk.token_count))
        self.conn.commit()

        # Get the ID (either new or existing)
        cursor = self.conn.execute(
            'SELECT id FROM chunks WHERE video_id = ? AND chunk_index = ?',
            (chunk.video_id, chunk.chunk_index)
        )
        return cursor.fetchone()[0]

    def save_chunks(self, chunks: list[Chunk]) -> list[int]:
        """Save multiple chunks atomically and return their IDs."""
        logger.debug(f"Saving {len(chunks)} chunks")
        ids = []
        with self.transaction():
            for chunk in chunks:
                self.conn.execute('''
                    INSERT INTO chunks (video_id, chunk_index, text, start_time, end_time, token_count)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(video_id, chunk_index) DO UPDATE SET
                        text=excluded.text,
                        start_time=excluded.start_time,
                        end_time=excluded.end_time,
                        token_count=excluded.token_count
                ''', (chunk.video_id, chunk.chunk_index, chunk.text,
                      chunk.start_time, chunk.end_time, chunk.token_count))

        # Get all IDs after commit
        for chunk in chunks:
            cursor = self.conn.execute(
                'SELECT id FROM chunks WHERE video_id = ? AND chunk_index = ?',
                (chunk.video_id, chunk.chunk_index)
            )
            ids.append(cursor.fetchone()[0])
        return ids

    def get_chunk(self, chunk_id: int) -> Optional[Chunk]:
        """Get a chunk by ID."""
        cursor = self.conn.execute(
            'SELECT * FROM chunks WHERE id = ?', (chunk_id,)
        )
        row = cursor.fetchone()
        if row:
            return self._row_to_chunk(row)
        return None

    def delete_chunk(self, chunk_id: int) -> bool:
        """Delete a chunk and its associations.

        Returns:
            True if chunk was deleted, False if not found
        """
        logger.debug(f"Deleting chunk: {chunk_id}")
        cursor = self.conn.execute(
            'DELETE FROM chunks WHERE id = ?', (chunk_id,)
        )
        self.conn.commit()
        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Deleted chunk: {chunk_id}")
        return deleted

    def get_chunks_for_video(self, video_id: str) -> list[Chunk]:
        """Get all chunks for a video."""
        cursor = self.conn.execute(
            'SELECT * FROM chunks WHERE video_id = ? ORDER BY chunk_index',
            (video_id,)
        )
        return [self._row_to_chunk(row) for row in cursor.fetchall()]

    def get_all_chunks(self) -> list[Chunk]:
        """Get all chunks."""
        cursor = self.conn.execute('SELECT * FROM chunks ORDER BY video_id, chunk_index')
        return [self._row_to_chunk(row) for row in cursor.fetchall()]

    def get_chunks_without_embeddings(self, embedded_ids: set[int]) -> list[Chunk]:
        """Get chunks that haven't been embedded yet."""
        all_chunks = self.get_all_chunks()
        return [c for c in all_chunks if c.id not in embedded_ids]

    def _row_to_chunk(self, row: sqlite3.Row) -> Chunk:
        """Convert a database row to a Chunk object."""
        return Chunk(
            id=row['id'],
            video_id=row['video_id'],
            chunk_index=row['chunk_index'],
            text=row['text'],
            start_time=row['start_time'],
            end_time=row['end_time'],
            token_count=row['token_count'],
            created_at=row['created_at'],
        )

    # ==================== CHUNK METADATA OPERATIONS ====================

    def save_chunk_metadata(self, chunk_id: int, main_theme: str, summary: str):
        """Save extracted metadata for a chunk."""
        logger.debug(f"Saving metadata for chunk: {chunk_id}")
        self.conn.execute('''
            INSERT INTO chunk_metadata (chunk_id, main_theme, summary)
            VALUES (?, ?, ?)
            ON CONFLICT(chunk_id) DO UPDATE SET
                main_theme=excluded.main_theme,
                summary=excluded.summary,
                extracted_at=CURRENT_TIMESTAMP
        ''', (chunk_id, main_theme, summary))
        self.conn.commit()

    def get_chunk_metadata(self, chunk_id: int) -> Optional[dict]:
        """Get metadata for a chunk."""
        cursor = self.conn.execute(
            'SELECT main_theme, summary, extracted_at FROM chunk_metadata WHERE chunk_id = ?',
            (chunk_id,)
        )
        row = cursor.fetchone()
        if row:
            return {
                'main_theme': row['main_theme'],
                'summary': row['summary'],
                'extracted_at': row['extracted_at'],
            }
        return None

    def get_chunks_without_metadata(self) -> list[int]:
        """Get IDs of chunks that haven't been analyzed for topics."""
        cursor = self.conn.execute('''
            SELECT c.id FROM chunks c
            LEFT JOIN chunk_metadata cm ON c.id = cm.chunk_id
            WHERE cm.chunk_id IS NULL
        ''')
        return [row['id'] for row in cursor.fetchall()]

    # ==================== TOPIC OPERATIONS ====================

    def save_topic(self, topic: Topic) -> int:
        """Save or update a topic and return its ID."""
        logger.debug(f"Saving topic: {topic.name}")
        cursor = self.conn.execute('''
            INSERT INTO topics (name, description, category, parent_topic_id, confidence, mention_count)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                description=COALESCE(excluded.description, topics.description),
                category=excluded.category,
                confidence=MAX(excluded.confidence, topics.confidence),
                mention_count=topics.mention_count + 1
        ''', (topic.name, topic.description, topic.category.value,
              topic.parent_topic_id, topic.confidence, topic.mention_count))
        self.conn.commit()

        cursor = self.conn.execute('SELECT id FROM topics WHERE name = ?', (topic.name,))
        return cursor.fetchone()[0]

    def get_topic(self, topic_id: int) -> Optional[Topic]:
        """Get a topic by ID."""
        cursor = self.conn.execute('SELECT * FROM topics WHERE id = ?', (topic_id,))
        row = cursor.fetchone()
        if row:
            return self._row_to_topic(row)
        return None

    def get_topic_by_name(self, name: str) -> Optional[Topic]:
        """Get a topic by name."""
        cursor = self.conn.execute('SELECT * FROM topics WHERE name = ?', (name,))
        row = cursor.fetchone()
        if row:
            return self._row_to_topic(row)
        return None

    def get_all_topics(self) -> list[Topic]:
        """Get all topics ordered by mention count."""
        cursor = self.conn.execute('SELECT * FROM topics ORDER BY mention_count DESC')
        return [self._row_to_topic(row) for row in cursor.fetchall()]

    def _row_to_topic(self, row: sqlite3.Row) -> Topic:
        """Convert a database row to a Topic object."""
        return Topic(
            id=row['id'],
            name=row['name'],
            description=row['description'],
            category=TopicCategory(row['category']) if row['category'] else TopicCategory.CONCEPT,
            parent_topic_id=row['parent_topic_id'],
            confidence=row['confidence'],
            mention_count=row['mention_count'],
            created_at=row['created_at'],
        )

    # ==================== CHUNK-TOPIC OPERATIONS ====================

    def link_chunk_topic(self, chunk_id: int, topic_id: int, relevance_score: float = 1.0):
        """Link a chunk to a topic."""
        self.conn.execute('''
            INSERT INTO chunk_topics (chunk_id, topic_id, relevance_score)
            VALUES (?, ?, ?)
            ON CONFLICT(chunk_id, topic_id) DO UPDATE SET
                relevance_score = MAX(excluded.relevance_score, chunk_topics.relevance_score)
        ''', (chunk_id, topic_id, relevance_score))
        self.conn.commit()

    def get_topics_for_chunk(self, chunk_id: int) -> list[tuple[Topic, float]]:
        """Get all topics for a chunk with relevance scores."""
        cursor = self.conn.execute('''
            SELECT t.*, ct.relevance_score
            FROM topics t
            JOIN chunk_topics ct ON t.id = ct.topic_id
            WHERE ct.chunk_id = ?
            ORDER BY ct.relevance_score DESC
        ''', (chunk_id,))
        results = []
        for row in cursor.fetchall():
            topic = self._row_to_topic(row)
            results.append((topic, row['relevance_score']))
        return results

    def get_chunks_for_topic(self, topic_id: int) -> list[tuple[Chunk, float]]:
        """Get all chunks for a topic with relevance scores."""
        cursor = self.conn.execute('''
            SELECT c.*, ct.relevance_score
            FROM chunks c
            JOIN chunk_topics ct ON c.id = ct.chunk_id
            WHERE ct.topic_id = ?
            ORDER BY ct.relevance_score DESC
        ''', (topic_id,))
        results = []
        for row in cursor.fetchall():
            chunk = self._row_to_chunk(row)
            results.append((chunk, row['relevance_score']))
        return results

    # ==================== DUPLICATE GROUP OPERATIONS ====================

    def save_duplicate_group(self, group: DuplicateGroup) -> int:
        """Save a duplicate group atomically and return its ID."""
        logger.debug(f"Saving duplicate group: {group.group_hash}")
        with self.transaction():
            self.conn.execute('''
                INSERT INTO duplicate_groups (group_hash, canonical_chunk_id, merged_content)
                VALUES (?, ?, ?)
                ON CONFLICT(group_hash) DO UPDATE SET
                    canonical_chunk_id=excluded.canonical_chunk_id,
                    merged_content=excluded.merged_content
            ''', (group.group_hash, group.canonical_chunk_id, group.merged_content))

            cursor = self.conn.execute(
                'SELECT id FROM duplicate_groups WHERE group_hash = ?',
                (group.group_hash,)
            )
            group_id = cursor.fetchone()[0]

            # Save members in same transaction
            for member in group.members:
                self.conn.execute('''
                    INSERT OR REPLACE INTO duplicate_group_members (group_id, chunk_id, similarity_score)
                    VALUES (?, ?, ?)
                ''', (group_id, member.chunk_id, member.similarity_score))

        return group_id

    def get_duplicate_group(self, group_id: int) -> Optional[DuplicateGroup]:
        """Get a duplicate group by ID with its members."""
        cursor = self.conn.execute(
            'SELECT * FROM duplicate_groups WHERE id = ?', (group_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None

        group = DuplicateGroup(
            id=row['id'],
            group_hash=row['group_hash'],
            canonical_chunk_id=row['canonical_chunk_id'],
            merged_content=row['merged_content'],
            created_at=row['created_at'],
        )

        # Get members
        cursor = self.conn.execute(
            'SELECT * FROM duplicate_group_members WHERE group_id = ?',
            (group_id,)
        )
        for member_row in cursor.fetchall():
            group.members.append(DuplicateGroupMember(
                group_id=member_row['group_id'],
                chunk_id=member_row['chunk_id'],
                similarity_score=member_row['similarity_score'],
            ))

        return group

    def get_all_duplicate_groups(self) -> list[DuplicateGroup]:
        """Get all duplicate groups."""
        cursor = self.conn.execute('SELECT id FROM duplicate_groups')
        return [self.get_duplicate_group(row['id']) for row in cursor.fetchall()]

    # ==================== COURSE OPERATIONS ====================

    def save_course(self, course: Course) -> int:
        """Save a course and return its ID."""
        logger.debug(f"Saving course: {course.title}")
        cursor = self.conn.execute('''
            INSERT INTO courses (title, description, target_audience, difficulty_level, status)
            VALUES (?, ?, ?, ?, ?)
        ''', (course.title, course.description, course.target_audience,
              course.difficulty_level.value, course.status.value))
        self.conn.commit()
        return cursor.lastrowid

    def save_module(self, module: Module) -> int:
        """Save a module and return its ID."""
        logger.debug(f"Saving module: {module.title}")
        cursor = self.conn.execute('''
            INSERT INTO modules (course_id, title, description, sequence_order, learning_objectives)
            VALUES (?, ?, ?, ?, ?)
        ''', (module.course_id, module.title, module.description,
              module.sequence_order, json.dumps(module.learning_objectives)))
        self.conn.commit()
        return cursor.lastrowid

    def save_lesson(self, lesson: Lesson) -> int:
        """Save a lesson and return its ID."""
        logger.debug(f"Saving lesson: {lesson.title}")
        cursor = self.conn.execute('''
            INSERT INTO lessons (module_id, title, sequence_order, content, summary,
                                key_takeaways, estimated_duration, difficulty_level)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (lesson.module_id, lesson.title, lesson.sequence_order, lesson.content,
              lesson.summary, json.dumps(lesson.key_takeaways),
              lesson.estimated_duration, lesson.difficulty_level.value))
        self.conn.commit()
        return cursor.lastrowid

    def update_lesson(self, lesson_id: int, **fields) -> bool:
        """Update specific fields of a lesson.

        Args:
            lesson_id: Lesson ID to update
            **fields: Fields to update

        Returns:
            True if lesson was updated, False if not found
        """
        if not fields:
            return False

        valid_fields = {
            'title', 'sequence_order', 'content', 'summary',
            'key_takeaways', 'estimated_duration', 'difficulty_level'
        }

        updates = {k: v for k, v in fields.items() if k in valid_fields}
        if not updates:
            return False

        # Handle special fields
        if 'key_takeaways' in updates:
            updates['key_takeaways'] = json.dumps(updates['key_takeaways'])
        if 'difficulty_level' in updates and hasattr(updates['difficulty_level'], 'value'):
            updates['difficulty_level'] = updates['difficulty_level'].value

        set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
        values = list(updates.values()) + [lesson_id]

        cursor = self.conn.execute(
            f'UPDATE lessons SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
            values
        )
        self.conn.commit()

        updated = cursor.rowcount > 0
        if updated:
            logger.debug(f"Updated lesson {lesson_id}: {list(updates.keys())}")
        return updated

    def save_lesson_source(self, source: LessonSource) -> int:
        """Save a lesson source reference."""
        cursor = self.conn.execute('''
            INSERT INTO lesson_sources (lesson_id, chunk_id, usage_type, relevance_score, quote)
            VALUES (?, ?, ?, ?, ?)
        ''', (source.lesson_id, source.chunk_id, source.usage_type.value,
              source.relevance_score, source.quote))
        self.conn.commit()
        return cursor.lastrowid

    def get_course(self, course_id: int) -> Optional[Course]:
        """Get a full course with modules and lessons."""
        cursor = self.conn.execute('SELECT * FROM courses WHERE id = ?', (course_id,))
        row = cursor.fetchone()
        if not row:
            return None

        course = Course(
            id=row['id'],
            title=row['title'],
            description=row['description'],
            target_audience=row['target_audience'],
            difficulty_level=DifficultyLevel(row['difficulty_level']),
            status=CourseStatus(row['status']),
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )

        # Get modules
        cursor = self.conn.execute(
            'SELECT * FROM modules WHERE course_id = ? ORDER BY sequence_order',
            (course_id,)
        )
        for mod_row in cursor.fetchall():
            module = Module(
                id=mod_row['id'],
                course_id=mod_row['course_id'],
                title=mod_row['title'],
                description=mod_row['description'],
                sequence_order=mod_row['sequence_order'],
                learning_objectives=json.loads(mod_row['learning_objectives'] or '[]'),
            )

            # Get lessons for module
            les_cursor = self.conn.execute(
                'SELECT * FROM lessons WHERE module_id = ? ORDER BY sequence_order',
                (module.id,)
            )
            for les_row in les_cursor.fetchall():
                lesson = Lesson(
                    id=les_row['id'],
                    module_id=les_row['module_id'],
                    title=les_row['title'],
                    sequence_order=les_row['sequence_order'],
                    content=les_row['content'],
                    summary=les_row['summary'],
                    key_takeaways=json.loads(les_row['key_takeaways'] or '[]'),
                    estimated_duration=les_row['estimated_duration'],
                    difficulty_level=DifficultyLevel(les_row['difficulty_level']),
                )

                # Get sources for lesson
                src_cursor = self.conn.execute('''
                    SELECT ls.*, c.video_id, c.start_time, c.end_time, c.text
                    FROM lesson_sources ls
                    JOIN chunks c ON ls.chunk_id = c.id
                    WHERE ls.lesson_id = ?
                ''', (lesson.id,))
                for src_row in src_cursor.fetchall():
                    lesson.sources.append(LessonSource(
                        id=src_row['id'],
                        lesson_id=src_row['lesson_id'],
                        chunk_id=src_row['chunk_id'],
                        usage_type=SourceUsageType(src_row['usage_type']),
                        relevance_score=src_row['relevance_score'],
                        video_id=src_row['video_id'],
                        timestamp_start=src_row['start_time'],
                        timestamp_end=src_row['end_time'],
                        quote=src_row['quote'] or src_row['text'][:200],
                    ))

                module.lessons.append(lesson)
            course.modules.append(module)

        return course

    # ==================== COLLECTION OPERATIONS ====================

    def create_collection(self, collection: Collection) -> int:
        """Create a new collection and return its ID."""
        logger.debug(f"Creating collection: {collection.name} ({collection.slug})")
        cursor = self.conn.execute('''
            INSERT INTO collections (name, slug, description, collection_type, config)
            VALUES (?, ?, ?, ?, ?)
        ''', (collection.name, collection.slug, collection.description,
              collection.collection_type.value, json.dumps(collection.config)))
        self.conn.commit()
        logger.info(f"Created collection: {collection.slug}")
        return cursor.lastrowid

    def update_collection(self, slug: str, **fields) -> bool:
        """Update specific fields of a collection.

        Args:
            slug: Collection slug to update
            **fields: Fields to update (name, description, config)

        Returns:
            True if collection was updated, False if not found
        """
        if not fields:
            return False

        valid_fields = {'name', 'description', 'config', 'collection_type'}
        updates = {k: v for k, v in fields.items() if k in valid_fields}

        if not updates:
            return False

        # Handle special fields
        if 'config' in updates:
            updates['config'] = json.dumps(updates['config'])
        if 'collection_type' in updates and hasattr(updates['collection_type'], 'value'):
            updates['collection_type'] = updates['collection_type'].value

        set_clause = ', '.join(f'{k} = ?' for k in updates.keys())
        values = list(updates.values()) + [slug]

        cursor = self.conn.execute(
            f'UPDATE collections SET {set_clause}, updated_at = CURRENT_TIMESTAMP WHERE slug = ?',
            values
        )
        self.conn.commit()

        updated = cursor.rowcount > 0
        if updated:
            logger.debug(f"Updated collection {slug}: {list(updates.keys())}")
        return updated

    def get_collection(self, slug: str) -> Optional[Collection]:
        """Get a collection by slug."""
        cursor = self.conn.execute(
            'SELECT * FROM collections WHERE slug = ?', (slug,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_collection(row)

    def get_collection_by_id(self, collection_id: int) -> Optional[Collection]:
        """Get a collection by ID."""
        cursor = self.conn.execute(
            'SELECT * FROM collections WHERE id = ?', (collection_id,)
        )
        row = cursor.fetchone()
        if not row:
            return None
        return self._row_to_collection(row)

    def get_all_collections(self) -> list[Collection]:
        """Get all collections with stats (optimized query)."""
        # Single query to get all collections with aggregated stats
        cursor = self.conn.execute('''
            SELECT
                c.*,
                COUNT(DISTINCT cv.video_id) as video_count,
                COALESCE(SUM(v.duration), 0) as total_duration
            FROM collections c
            LEFT JOIN collection_videos cv ON c.id = cv.collection_id
            LEFT JOIN videos v ON cv.video_id = v.video_id
            GROUP BY c.id
            ORDER BY c.name
        ''')

        collections = []
        for row in cursor.fetchall():
            collection = self._row_to_collection(row)
            collection.video_count = row['video_count']
            collection.total_duration_hours = round((row['total_duration'] or 0) / 3600, 2)
            collections.append(collection)

        return collections

    def _row_to_collection(self, row: sqlite3.Row) -> Collection:
        """Convert a database row to a Collection object."""
        return Collection(
            id=row['id'],
            name=row['name'],
            slug=row['slug'],
            description=row['description'],
            collection_type=CollectionType(row['collection_type']) if row['collection_type'] else CollectionType.CUSTOM,
            config=json.loads(row['config']) if row['config'] else {},
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )

    def add_video_to_collection(self, collection_id: int, video_id: str, notes: str = ""):
        """Add a video to a collection."""
        logger.debug(f"Adding video {video_id} to collection {collection_id}")
        self.conn.execute('''
            INSERT OR IGNORE INTO collection_videos (collection_id, video_id, notes)
            VALUES (?, ?, ?)
        ''', (collection_id, video_id, notes))
        self.conn.commit()

    def remove_video_from_collection(self, collection_id: int, video_id: str):
        """Remove a video from a collection."""
        logger.debug(f"Removing video {video_id} from collection {collection_id}")
        self.conn.execute(
            'DELETE FROM collection_videos WHERE collection_id = ? AND video_id = ?',
            (collection_id, video_id)
        )
        self.conn.commit()

    def get_collection_videos(self, collection_id: int) -> list[str]:
        """Get all video IDs in a collection."""
        cursor = self.conn.execute(
            'SELECT video_id FROM collection_videos WHERE collection_id = ?',
            (collection_id,)
        )
        return [row['video_id'] for row in cursor.fetchall()]

    def get_collections_for_video(self, video_id: str) -> list[Collection]:
        """Get all collections that contain a video."""
        cursor = self.conn.execute('''
            SELECT c.* FROM collections c
            JOIN collection_videos cv ON c.id = cv.collection_id
            WHERE cv.video_id = ?
        ''', (video_id,))
        return [self._row_to_collection(row) for row in cursor.fetchall()]

    def get_collection_stats(self, collection_id: int) -> dict:
        """Get statistics for a specific collection (optimized)."""
        # Single query for all stats
        cursor = self.conn.execute('''
            SELECT
                COUNT(DISTINCT cv.video_id) as video_count,
                COUNT(DISTINCT ch.id) as chunk_count,
                COUNT(DISTINCT ct.topic_id) as topic_count,
                COALESCE(SUM(v.duration), 0) as total_duration
            FROM collection_videos cv
            LEFT JOIN videos v ON cv.video_id = v.video_id
            LEFT JOIN chunks ch ON cv.video_id = ch.video_id
            LEFT JOIN chunk_topics ct ON ch.id = ct.chunk_id
            WHERE cv.collection_id = ?
        ''', (collection_id,))

        row = cursor.fetchone()
        return {
            'video_count': row['video_count'] or 0,
            'chunk_count': row['chunk_count'] or 0,
            'topic_count': row['topic_count'] or 0,
            'duration_hours': round((row['total_duration'] or 0) / 3600, 2),
        }

    def get_chunks_for_collection(self, collection_id: int) -> list[Chunk]:
        """Get all chunks for videos in a collection."""
        video_ids = self.get_collection_videos(collection_id)
        if not video_ids:
            return []

        placeholders = ','.join('?' * len(video_ids))
        cursor = self.conn.execute(f'''
            SELECT * FROM chunks WHERE video_id IN ({placeholders})
            ORDER BY video_id, chunk_index
        ''', video_ids)
        return [self._row_to_chunk(row) for row in cursor.fetchall()]

    def delete_collection(self, collection_id: int) -> bool:
        """Delete a collection (but not its videos).

        Returns:
            True if collection was deleted, False if not found
        """
        logger.debug(f"Deleting collection: {collection_id}")
        with self.transaction():
            # CASCADE will handle collection_videos and collection_topics
            cursor = self.conn.execute(
                'DELETE FROM collections WHERE id = ?',
                (collection_id,)
            )

        deleted = cursor.rowcount > 0
        if deleted:
            logger.info(f"Deleted collection: {collection_id}")
        return deleted

    # ==================== STATS ====================

    def get_stats(self) -> dict:
        """Get course builder statistics."""
        stats = {}
        stats['chunk_count'] = self.conn.execute('SELECT COUNT(*) FROM chunks').fetchone()[0]
        stats['topic_count'] = self.conn.execute('SELECT COUNT(*) FROM topics').fetchone()[0]
        stats['duplicate_group_count'] = self.conn.execute('SELECT COUNT(*) FROM duplicate_groups').fetchone()[0]
        stats['course_count'] = self.conn.execute('SELECT COUNT(*) FROM courses').fetchone()[0]
        stats['videos_chunked'] = self.conn.execute('SELECT COUNT(DISTINCT video_id) FROM chunks').fetchone()[0]
        stats['collection_count'] = self.conn.execute('SELECT COUNT(*) FROM collections').fetchone()[0]
        return stats

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.debug("Database connection closed")
