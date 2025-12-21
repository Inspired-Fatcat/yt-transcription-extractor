"""Unified batch processor with checkpoint/resume support.

Features:
- Checkpoint/resume for interrupted batches
- Graceful shutdown on SIGINT/SIGTERM
- Progress callbacks
- Failed video tracking
- Configurable rate limiting
"""

import json
import signal
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional, List, Set
from enum import Enum

from .config import get_config
from .database import TranscriptDatabase
from .extractor import YouTubeExtractor, ExtractionResult
from .exceptions import RateLimitError
from .logging_config import get_logger

logger = get_logger('batch_processor')


class BatchStatus(Enum):
    """Status of a batch job."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


@dataclass
class BatchState:
    """Persistent state for a batch job."""
    batch_id: str
    status: BatchStatus
    video_ids: List[str]
    processed_ids: Set[str] = field(default_factory=set)
    failed_ids: Set[str] = field(default_factory=set)
    folder_name: Optional[str] = None
    collection_id: Optional[int] = None
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    completed_at: Optional[str] = None
    config: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            'batch_id': self.batch_id,
            'status': self.status.value,
            'video_ids': self.video_ids,
            'processed_ids': list(self.processed_ids),
            'failed_ids': list(self.failed_ids),
            'folder_name': self.folder_name,
            'collection_id': self.collection_id,
            'started_at': self.started_at,
            'updated_at': self.updated_at,
            'completed_at': self.completed_at,
            'config': self.config,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'BatchState':
        """Create from dictionary."""
        return cls(
            batch_id=data['batch_id'],
            status=BatchStatus(data['status']),
            video_ids=data['video_ids'],
            processed_ids=set(data.get('processed_ids', [])),
            failed_ids=set(data.get('failed_ids', [])),
            folder_name=data.get('folder_name'),
            collection_id=data.get('collection_id'),
            started_at=data.get('started_at'),
            updated_at=data.get('updated_at'),
            completed_at=data.get('completed_at'),
            config=data.get('config', {}),
        )

    @property
    def pending_ids(self) -> List[str]:
        """Get video IDs that haven't been processed yet."""
        processed = self.processed_ids | self.failed_ids
        return [vid for vid in self.video_ids if vid not in processed]

    @property
    def progress_percent(self) -> float:
        """Get completion percentage."""
        if not self.video_ids:
            return 100.0
        processed = len(self.processed_ids) + len(self.failed_ids)
        return (processed / len(self.video_ids)) * 100


@dataclass
class BatchResult:
    """Result of a batch processing run."""
    batch_id: str
    total_videos: int
    processed: int
    failed: int
    skipped: int
    interrupted: bool = False
    error: Optional[str] = None


class BatchProcessor:
    """Unified batch processor with checkpoint/resume support."""

    def __init__(
        self,
        db_path: Optional[str] = None,
        state_dir: Optional[str] = None,
        delay_between_videos: Optional[float] = None,
        delay_between_batches: Optional[float] = None,
        batch_size: Optional[int] = None,
        languages: Optional[List[str]] = None,
    ):
        """Initialize batch processor.

        Args:
            db_path: Path to database (default from config)
            state_dir: Directory for state files (default from config)
            delay_between_videos: Delay between videos in seconds
            delay_between_batches: Delay between batches in seconds
            batch_size: Number of videos per batch
            languages: Preferred transcript languages
        """
        config = get_config()

        self.db_path = db_path or config.database.path
        self.state_dir = Path(state_dir or config.batch.state_directory)
        self.delay_between_videos = delay_between_videos or config.batch.delay_between_videos
        self.delay_between_batches = delay_between_batches or config.batch.delay_between_batches
        self.batch_size = batch_size or config.batch.batch_size
        self.languages = languages or config.extraction.default_languages

        self.state_dir.mkdir(parents=True, exist_ok=True)

        self._interrupted = False
        self._current_state: Optional[BatchState] = None

        # Register signal handlers for graceful shutdown
        if config.batch.graceful_shutdown:
            signal.signal(signal.SIGINT, self._signal_handler)
            signal.signal(signal.SIGTERM, self._signal_handler)

        logger.info(f"BatchProcessor initialized (delay={self.delay_between_videos}s, batch_size={self.batch_size})")

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully."""
        sig_name = signal.Signals(signum).name
        logger.warning(f"Received {sig_name}, initiating graceful shutdown...")
        self._interrupted = True

    def _save_state(self, state: BatchState) -> None:
        """Save batch state to disk."""
        state.updated_at = datetime.utcnow().isoformat()
        state_path = self.state_dir / f"{state.batch_id}.json"

        with open(state_path, 'w') as f:
            json.dump(state.to_dict(), f, indent=2)

        logger.debug(f"Saved batch state: {state_path}")

    def _load_state(self, batch_id: str) -> Optional[BatchState]:
        """Load batch state from disk."""
        state_path = self.state_dir / f"{batch_id}.json"

        if not state_path.exists():
            return None

        try:
            with open(state_path, 'r') as f:
                data = json.load(f)
            return BatchState.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load state {batch_id}: {e}")
            return None

    def _generate_batch_id(self) -> str:
        """Generate a unique batch ID."""
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        return f"batch_{timestamp}"

    def list_batches(self) -> List[BatchState]:
        """List all batch jobs."""
        batches = []
        for state_file in self.state_dir.glob("batch_*.json"):
            state = self._load_state(state_file.stem)
            if state:
                batches.append(state)
        return sorted(batches, key=lambda x: x.started_at or '', reverse=True)

    def get_latest_batch(self) -> Optional[BatchState]:
        """Get the most recent batch."""
        batches = self.list_batches()
        return batches[0] if batches else None

    def get_resumable_batches(self) -> List[BatchState]:
        """Get batches that can be resumed."""
        return [
            b for b in self.list_batches()
            if b.status in (BatchStatus.IN_PROGRESS, BatchStatus.INTERRUPTED)
            and b.pending_ids
        ]

    def process(
        self,
        video_ids: List[str],
        folder_name: Optional[str] = None,
        collection_id: Optional[int] = None,
        skip_existing: bool = True,
        on_progress: Optional[Callable[[int, int, str, str], None]] = None,
        on_batch_complete: Optional[Callable[[int, int], None]] = None,
    ) -> BatchResult:
        """Process a batch of videos.

        Args:
            video_ids: List of video IDs to process
            folder_name: Optional folder name for organizing
            collection_id: Optional collection ID to add videos to
            skip_existing: Skip videos already in database
            on_progress: Callback (current, total, video_id, status)
            on_batch_complete: Callback (batch_number, total_batches)

        Returns:
            BatchResult with processing statistics
        """
        batch_id = self._generate_batch_id()
        state = BatchState(
            batch_id=batch_id,
            status=BatchStatus.IN_PROGRESS,
            video_ids=video_ids,
            folder_name=folder_name,
            collection_id=collection_id,
            started_at=datetime.utcnow().isoformat(),
            config={
                'delay_between_videos': self.delay_between_videos,
                'delay_between_batches': self.delay_between_batches,
                'batch_size': self.batch_size,
                'skip_existing': skip_existing,
            },
        )

        return self._run_batch(state, skip_existing, on_progress, on_batch_complete)

    def resume(
        self,
        batch_id: Optional[str] = None,
        on_progress: Optional[Callable[[int, int, str, str], None]] = None,
        on_batch_complete: Optional[Callable[[int, int], None]] = None,
    ) -> BatchResult:
        """Resume a previously interrupted batch.

        Args:
            batch_id: Specific batch ID to resume (default: latest resumable)
            on_progress: Callback (current, total, video_id, status)
            on_batch_complete: Callback (batch_number, total_batches)

        Returns:
            BatchResult with processing statistics
        """
        if batch_id:
            state = self._load_state(batch_id)
        else:
            resumable = self.get_resumable_batches()
            state = resumable[0] if resumable else None

        if not state:
            logger.warning("No resumable batch found")
            return BatchResult(
                batch_id="",
                total_videos=0,
                processed=0,
                failed=0,
                skipped=0,
                error="No resumable batch found"
            )

        if not state.pending_ids:
            logger.info(f"Batch {state.batch_id} already completed")
            return BatchResult(
                batch_id=state.batch_id,
                total_videos=len(state.video_ids),
                processed=len(state.processed_ids),
                failed=len(state.failed_ids),
                skipped=0,
            )

        logger.info(f"Resuming batch {state.batch_id} ({len(state.pending_ids)} remaining)")
        state.status = BatchStatus.IN_PROGRESS
        skip_existing = state.config.get('skip_existing', True)

        return self._run_batch(state, skip_existing, on_progress, on_batch_complete)

    def retry_failed(
        self,
        batch_id: Optional[str] = None,
        on_progress: Optional[Callable[[int, int, str, str], None]] = None,
    ) -> BatchResult:
        """Retry failed videos from a batch.

        Args:
            batch_id: Specific batch ID (default: latest with failures)

        Returns:
            BatchResult with processing statistics
        """
        if batch_id:
            state = self._load_state(batch_id)
        else:
            # Find latest batch with failures
            for batch in self.list_batches():
                if batch.failed_ids:
                    state = batch
                    break
            else:
                state = None

        if not state or not state.failed_ids:
            logger.warning("No failed videos to retry")
            return BatchResult(
                batch_id="",
                total_videos=0,
                processed=0,
                failed=0,
                skipped=0,
                error="No failed videos to retry"
            )

        # Create new batch with just the failed videos
        retry_ids = list(state.failed_ids)
        logger.info(f"Retrying {len(retry_ids)} failed videos from {state.batch_id}")

        # Clear failed status for these videos
        state.failed_ids.clear()
        state.video_ids = retry_ids
        self._save_state(state)

        return self._run_batch(state, skip_existing=False, on_progress=on_progress)

    def _run_batch(
        self,
        state: BatchState,
        skip_existing: bool,
        on_progress: Optional[Callable[[int, int, str, str], None]] = None,
        on_batch_complete: Optional[Callable[[int, int], None]] = None,
    ) -> BatchResult:
        """Execute batch processing."""
        self._current_state = state
        self._interrupted = False

        pending_ids = state.pending_ids
        total = len(state.video_ids)
        processed_count = len(state.processed_ids)
        failed_count = len(state.failed_ids)
        skipped_count = 0

        # Calculate batches
        batches = [
            pending_ids[i:i + self.batch_size]
            for i in range(0, len(pending_ids), self.batch_size)
        ]

        logger.info(f"Processing {len(pending_ids)} videos in {len(batches)} batches")

        with TranscriptDatabase(self.db_path) as db:
            extractor = YouTubeExtractor(
                db_path=self.db_path,
                languages=self.languages,
                delay_between_requests=self.delay_between_videos,
            )

            try:
                for batch_num, batch_ids in enumerate(batches, 1):
                    if self._interrupted:
                        break

                    logger.info(f"Starting batch {batch_num}/{len(batches)}")

                    for video_id in batch_ids:
                        if self._interrupted:
                            break

                        current_num = processed_count + failed_count + skipped_count + 1

                        # Progress callback
                        if on_progress:
                            on_progress(current_num, total, video_id, "processing...")

                        # Process video
                        result = extractor.process_video(
                            video_id,
                            skip_existing=skip_existing,
                        )

                        # Update counts
                        if result.success:
                            state.processed_ids.add(video_id)
                            if result.has_transcript:
                                processed_count += 1
                            else:
                                processed_count += 1  # Still successful even without transcript
                        else:
                            state.failed_ids.add(video_id)
                            failed_count += 1

                        # Add to collection if specified
                        if result.success and state.collection_id:
                            from course_builder.core.database import CourseDatabase
                            with CourseDatabase(self.db_path) as cdb:
                                cdb.add_video_to_collection(state.collection_id, video_id)

                        # Update progress
                        if on_progress:
                            status = "done" if result.success else f"failed: {result.error}"
                            on_progress(current_num, total, video_id, status)

                        # Save state periodically
                        if current_num % 5 == 0:
                            self._save_state(state)

                    # Batch complete callback
                    if on_batch_complete and not self._interrupted:
                        on_batch_complete(batch_num, len(batches))

                    # Delay between batches
                    if batch_num < len(batches) and not self._interrupted:
                        logger.info(f"Batch {batch_num} complete, waiting {self.delay_between_batches}s...")
                        time.sleep(self.delay_between_batches)

            finally:
                extractor.close()

        # Final state update
        if self._interrupted:
            state.status = BatchStatus.INTERRUPTED
            logger.warning(f"Batch {state.batch_id} interrupted")
        elif state.pending_ids:
            state.status = BatchStatus.INTERRUPTED
        else:
            state.status = BatchStatus.COMPLETED
            state.completed_at = datetime.utcnow().isoformat()
            logger.info(f"Batch {state.batch_id} completed")

        self._save_state(state)
        self._current_state = None

        return BatchResult(
            batch_id=state.batch_id,
            total_videos=total,
            processed=processed_count,
            failed=failed_count,
            skipped=skipped_count,
            interrupted=self._interrupted,
        )

    def get_status(self, batch_id: Optional[str] = None) -> Optional[dict]:
        """Get status of a batch.

        Args:
            batch_id: Batch ID (default: latest)

        Returns:
            Status dictionary or None
        """
        state = self._load_state(batch_id) if batch_id else self.get_latest_batch()

        if not state:
            return None

        return {
            'batch_id': state.batch_id,
            'status': state.status.value,
            'total': len(state.video_ids),
            'processed': len(state.processed_ids),
            'failed': len(state.failed_ids),
            'pending': len(state.pending_ids),
            'progress': f"{state.progress_percent:.1f}%",
            'folder': state.folder_name,
            'started_at': state.started_at,
            'updated_at': state.updated_at,
            'completed_at': state.completed_at,
        }

    def cleanup_completed(self, days_old: int = 30) -> int:
        """Remove state files for completed batches older than specified days.

        Args:
            days_old: Remove batches older than this many days

        Returns:
            Number of state files removed
        """
        from datetime import timedelta

        cutoff = datetime.utcnow() - timedelta(days=days_old)
        removed = 0

        for state in self.list_batches():
            if state.status == BatchStatus.COMPLETED and state.completed_at:
                completed = datetime.fromisoformat(state.completed_at.replace('Z', '+00:00').replace('+00:00', ''))
                if completed < cutoff:
                    state_path = self.state_dir / f"{state.batch_id}.json"
                    state_path.unlink(missing_ok=True)
                    removed += 1
                    logger.debug(f"Removed old state file: {state.batch_id}")

        logger.info(f"Cleaned up {removed} old batch state files")
        return removed
