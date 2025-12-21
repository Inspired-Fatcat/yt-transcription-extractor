#!/usr/bin/env python3
"""
Batch processing CLI for YouTube Transcription Extractor.

Provides a unified interface for batch extraction with:
- Checkpoint/resume support
- Graceful shutdown handling
- Failed video retry
- Progress tracking

Usage:
    python batch.py process videos.txt --folder "My Videos"
    python batch.py process --playlist URL -f "Course Name"
    python batch.py resume                    # Resume latest
    python batch.py resume batch_20231220     # Resume specific
    python batch.py status                    # Show status
    python batch.py retry-failed              # Retry failed videos
    python batch.py list                      # List all batches
"""

import argparse
import sys
from pathlib import Path

from src.batch_processor import BatchProcessor, BatchStatus
from src.logging_config import setup_logging, get_logger
from src.config import get_config
from src.video_info import get_playlist_video_ids

logger = get_logger('batch_cli')


def print_progress(current: int, total: int, video_id: str, status: str):
    """Print progress to console."""
    pct = (current / total * 100) if total > 0 else 0
    print(f"[{current}/{total}] ({pct:.0f}%) {video_id}: {status}")


def print_batch_complete(batch_num: int, total_batches: int):
    """Print batch completion message."""
    print(f"\n=== Batch {batch_num}/{total_batches} complete ===\n")


def load_video_list(filepath: str) -> list[str]:
    """Load video URLs/IDs from a text file."""
    path = Path(filepath)
    if not path.exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    videos = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#'):
                videos.append(line)

    return videos


def cmd_process(args):
    """Process videos command."""
    # Collect video IDs
    video_ids = []

    if args.input_file:
        video_ids.extend(load_video_list(args.input_file))

    if args.playlist:
        print(f"Fetching playlist: {args.playlist}")
        try:
            playlist_ids = get_playlist_video_ids(args.playlist)
            video_ids.extend(playlist_ids)
            print(f"Found {len(playlist_ids)} videos in playlist")
        except Exception as e:
            print(f"Error fetching playlist: {e}")
            sys.exit(1)

    if args.video:
        video_ids.extend(args.video)

    if not video_ids:
        print("Error: No videos to process. Provide a file, playlist, or video IDs.")
        sys.exit(1)

    # Handle collection/folder
    collection_id = None
    if args.folder and not args.no_folder:
        from course_builder.core.database import CourseDatabase
        from course_builder.models import Collection, CollectionType
        import re

        def slugify(name: str) -> str:
            slug = name.lower()
            slug = re.sub(r'[\s_]+', '-', slug)
            slug = re.sub(r'[^a-z0-9-]', '', slug)
            slug = re.sub(r'-+', '-', slug)
            return slug.strip('-') or 'unnamed'

        config = get_config()
        with CourseDatabase(config.database.path) as cdb:
            slug = slugify(args.folder)
            existing = cdb.get_collection(slug)
            if existing:
                collection_id = existing.id
                print(f"Adding to existing folder: {existing.name}")
            else:
                new_collection = Collection(
                    name=args.folder,
                    slug=slug,
                    description=f"Batch extraction: {args.folder}",
                    collection_type=CollectionType.CUSTOM,
                )
                collection_id = cdb.create_collection(new_collection)
                print(f"Created new folder: {args.folder}")

    # Create processor
    processor = BatchProcessor(
        delay_between_videos=args.delay,
        batch_size=args.batch_size,
    )

    print(f"\nProcessing {len(video_ids)} video(s)...")
    print(f"Delay: {args.delay}s between videos, {processor.delay_between_batches}s between batches")
    print(f"Batch size: {args.batch_size}")
    print()

    # Process
    result = processor.process(
        video_ids=video_ids,
        folder_name=args.folder,
        collection_id=collection_id,
        skip_existing=not args.no_skip,
        on_progress=print_progress,
        on_batch_complete=print_batch_complete,
    )

    # Summary
    print("\n=== Summary ===")
    print(f"Batch ID: {result.batch_id}")
    print(f"Total: {result.total_videos}")
    print(f"Processed: {result.processed}")
    print(f"Failed: {result.failed}")
    print(f"Skipped: {result.skipped}")

    if result.interrupted:
        print("\nBatch was interrupted. Resume with:")
        print(f"  python batch.py resume {result.batch_id}")

    if result.failed > 0:
        print("\nRetry failed videos with:")
        print(f"  python batch.py retry-failed {result.batch_id}")


def cmd_resume(args):
    """Resume a batch command."""
    processor = BatchProcessor()

    batch_id = args.batch_id

    if not batch_id:
        resumable = processor.get_resumable_batches()
        if not resumable:
            print("No resumable batches found.")
            return
        batch_id = resumable[0].batch_id
        print(f"Resuming latest batch: {batch_id}")

    result = processor.resume(
        batch_id=batch_id,
        on_progress=print_progress,
        on_batch_complete=print_batch_complete,
    )

    if result.error:
        print(f"Error: {result.error}")
        return

    # Summary
    print("\n=== Summary ===")
    print(f"Batch ID: {result.batch_id}")
    print(f"Processed: {result.processed}")
    print(f"Failed: {result.failed}")

    if result.interrupted:
        print("\nBatch was interrupted. Resume again with:")
        print(f"  python batch.py resume {result.batch_id}")


def cmd_retry_failed(args):
    """Retry failed videos command."""
    processor = BatchProcessor()

    result = processor.retry_failed(
        batch_id=args.batch_id,
        on_progress=print_progress,
    )

    if result.error:
        print(f"Error: {result.error}")
        return

    print("\n=== Summary ===")
    print(f"Retried: {result.total_videos}")
    print(f"Succeeded: {result.processed}")
    print(f"Failed: {result.failed}")


def cmd_status(args):
    """Show batch status command."""
    processor = BatchProcessor()

    status = processor.get_status(args.batch_id)

    if not status:
        print("No batch found.")
        return

    print(f"\n=== Batch Status ===")
    print(f"Batch ID:   {status['batch_id']}")
    print(f"Status:     {status['status']}")
    print(f"Progress:   {status['progress']}")
    print(f"Processed:  {status['processed']}/{status['total']}")
    print(f"Failed:     {status['failed']}")
    print(f"Pending:    {status['pending']}")
    if status['folder']:
        print(f"Folder:     {status['folder']}")
    print(f"Started:    {status['started_at']}")
    if status['completed_at']:
        print(f"Completed:  {status['completed_at']}")


def cmd_list(args):
    """List all batches command."""
    processor = BatchProcessor()
    batches = processor.list_batches()

    if not batches:
        print("No batches found.")
        return

    print(f"\n{'Batch ID':<25} {'Status':<12} {'Progress':<10} {'Folder':<20}")
    print("-" * 70)

    for batch in batches[:args.limit]:
        progress = f"{batch.progress_percent:.0f}%"
        folder = batch.folder_name or "-"
        if len(folder) > 18:
            folder = folder[:15] + "..."
        print(f"{batch.batch_id:<25} {batch.status.value:<12} {progress:<10} {folder:<20}")


def cmd_cleanup(args):
    """Clean up old batch state files."""
    processor = BatchProcessor()
    removed = processor.cleanup_completed(days_old=args.days)
    print(f"Removed {removed} old state files.")


def main():
    parser = argparse.ArgumentParser(
        description="Batch processing for YouTube Transcription Extractor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        '--verbose', '-V',
        action='store_true',
        help='Enable verbose output'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to run')

    # Process command
    process_parser = subparsers.add_parser(
        'process',
        help='Process a batch of videos'
    )
    process_parser.add_argument(
        'input_file',
        nargs='?',
        help='Text file with video URLs/IDs (one per line)'
    )
    process_parser.add_argument(
        '--playlist', '-p',
        help='YouTube playlist URL'
    )
    process_parser.add_argument(
        '--video', '-v',
        action='append',
        help='Single video URL/ID (can be used multiple times)'
    )
    process_parser.add_argument(
        '--folder', '-f',
        help='Folder/collection name to organize videos'
    )
    process_parser.add_argument(
        '--no-folder',
        action='store_true',
        help='Skip folder organization'
    )
    process_parser.add_argument(
        '--delay',
        type=float,
        default=60.0,
        help='Delay between videos in seconds (default: 60)'
    )
    process_parser.add_argument(
        '--batch-size',
        type=int,
        default=10,
        help='Number of videos per batch (default: 10)'
    )
    process_parser.add_argument(
        '--no-skip',
        action='store_true',
        help='Re-process videos already in database'
    )

    # Resume command
    resume_parser = subparsers.add_parser(
        'resume',
        help='Resume an interrupted batch'
    )
    resume_parser.add_argument(
        'batch_id',
        nargs='?',
        help='Batch ID to resume (default: latest)'
    )

    # Retry-failed command
    retry_parser = subparsers.add_parser(
        'retry-failed',
        help='Retry failed videos from a batch'
    )
    retry_parser.add_argument(
        'batch_id',
        nargs='?',
        help='Batch ID (default: latest with failures)'
    )

    # Status command
    status_parser = subparsers.add_parser(
        'status',
        help='Show batch status'
    )
    status_parser.add_argument(
        'batch_id',
        nargs='?',
        help='Batch ID (default: latest)'
    )

    # List command
    list_parser = subparsers.add_parser(
        'list',
        help='List all batches'
    )
    list_parser.add_argument(
        '--limit', '-n',
        type=int,
        default=10,
        help='Maximum batches to show (default: 10)'
    )

    # Cleanup command
    cleanup_parser = subparsers.add_parser(
        'cleanup',
        help='Remove old batch state files'
    )
    cleanup_parser.add_argument(
        '--days',
        type=int,
        default=30,
        help='Remove batches older than this many days (default: 30)'
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Initialize logging
    log_level = "DEBUG" if args.verbose else "INFO"
    config = get_config()
    setup_logging(
        level=log_level,
        log_file=config.logging.file,
        console=True
    )

    # Route to command handler
    commands = {
        'process': cmd_process,
        'resume': cmd_resume,
        'retry-failed': cmd_retry_failed,
        'status': cmd_status,
        'list': cmd_list,
        'cleanup': cmd_cleanup,
    }

    try:
        commands[args.command](args)
    except KeyboardInterrupt:
        print("\n\nInterrupted by user.")
        sys.exit(130)
    except Exception as e:
        logger.exception(f"Error: {e}")
        print(f"\nError: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
