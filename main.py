#!/usr/bin/env python3
"""
YouTube Transcription Extractor

Extract transcripts from YouTube videos and store them in a searchable database.

Usage:
    python main.py videos.txt              # Process videos (prompts for folder)
    python main.py videos.txt -f "AI Dev"  # Process videos into "AI Dev" folder
    python main.py --playlist URL          # Process entire playlist
    python main.py --search "query"        # Search transcripts
    python main.py --stats                 # Show database statistics
    python main.py videos.txt --no-folder  # Process without folder organization
"""

import argparse
import re
import sys
from pathlib import Path

from src.extractor import YouTubeExtractor
from src.logging_config import setup_logging, get_logger
from src.exceptions import PlaylistError, TranscriptExtractorError
from course_builder.core.database import CourseDatabase
from course_builder.models import Collection, CollectionType

# Initialize logging (will be configured in main())
logger = get_logger('main')


def print_progress(current: int, total: int, video_id: str, status: str):
    """Print progress to console."""
    if total > 0:
        print(f"[{current}/{total}] {video_id}: {status}")
    else:
        print(f"{video_id}: {status}")


def slugify(name: str) -> str:
    """Convert a name to a URL-friendly slug."""
    # Convert to lowercase
    slug = name.lower()
    # Replace spaces and underscores with hyphens
    slug = re.sub(r'[\s_]+', '-', slug)
    # Remove non-alphanumeric characters (except hyphens)
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    # Remove multiple consecutive hyphens
    slug = re.sub(r'-+', '-', slug)
    # Strip leading/trailing hyphens
    slug = slug.strip('-')
    return slug or 'unnamed'


def prompt_for_folder(course_db: CourseDatabase) -> tuple[str, str]:
    """
    Prompt user for folder name and return (name, slug).
    Shows existing collections for reference.
    """
    # Show existing collections
    collections = course_db.get_all_collections()
    if collections:
        print("\n=== Existing Folders ===")
        for c in collections:
            print(f"  - {c.name} ({c.slug}) - {c.video_count} videos")
        print()

    print("Enter a folder name for these extractions.")
    print("(Use an existing name to add to that folder, or enter a new name)")

    while True:
        folder_name = input("\nFolder name: ").strip()
        if folder_name:
            return folder_name, slugify(folder_name)
        print("Folder name cannot be empty. Please try again.")


def load_video_list(filepath: str) -> list[str]:
    """Load video URLs/IDs from a text file (one per line)."""
    path = Path(filepath)
    if not path.exists():
        print(f"Error: File not found: {filepath}")
        sys.exit(1)

    videos = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            # Skip empty lines and comments
            if line and not line.startswith('#'):
                videos.append(line)

    return videos


def main():
    parser = argparse.ArgumentParser(
        description="Extract YouTube video transcripts into a database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
    python main.py videos.txt                        # Prompts for folder name
    python main.py videos.txt -f "AI Development"   # Saves to "AI Development" folder
    python main.py --playlist "https://youtube.com/playlist?list=PLxxxx"
    python main.py --video "https://youtube.com/watch?v=xxxxx" -f "Tutorials"
    python main.py --search "machine learning"
    python main.py --stats
    python main.py videos.txt --no-folder           # Skip folder organization
        """
    )

    parser.add_argument(
        'input_file',
        nargs='?',
        help='Text file with YouTube URLs/IDs (one per line)'
    )
    parser.add_argument(
        '--playlist', '-p',
        help='Process all videos from a YouTube playlist URL'
    )
    parser.add_argument(
        '--video', '-v',
        action='append',
        help='Process a single video (can be used multiple times)'
    )
    parser.add_argument(
        '--search', '-s',
        help='Search transcripts for a query'
    )
    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show database statistics'
    )
    parser.add_argument(
        '--db',
        default='data/transcripts.db',
        help='Database file path (default: data/transcripts.db)'
    )
    parser.add_argument(
        '--language', '-l',
        action='append',
        default=[],
        help='Preferred transcript language(s) (default: en)'
    )
    parser.add_argument(
        '--no-skip',
        action='store_true',
        help='Re-process videos even if already in database'
    )
    parser.add_argument(
        '--delay',
        type=float,
        default=1.0,
        help='Delay between requests in seconds (default: 1.0)'
    )
    parser.add_argument(
        '--folder', '-f',
        help='Folder/collection name to organize extractions (will prompt if not provided)'
    )
    parser.add_argument(
        '--no-folder',
        action='store_true',
        help='Skip folder assignment (do not prompt for folder)'
    )
    parser.add_argument(
        '--verbose', '-V',
        action='store_true',
        help='Enable verbose output (DEBUG level logging)'
    )
    parser.add_argument(
        '--log-file',
        help='Write logs to file (default: no file logging)'
    )

    args = parser.parse_args()

    # Initialize logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(
        level=log_level,
        log_file=args.log_file,
        console=True
    )
    logger.info("YT Transcription Extractor starting")

    # Determine languages
    languages = args.language if args.language else ['en']

    # Initialize extractor
    extractor = YouTubeExtractor(
        db_path=args.db,
        languages=languages,
        delay_between_requests=args.delay,
    )

    try:
        # Handle different modes
        if args.stats:
            stats = extractor.get_stats()
            print("\n=== Database Statistics ===")
            print(f"Videos:          {stats['video_count']}")
            print(f"Transcripts:     {stats['transcript_count']}")
            print(f"Unique Channels: {stats['unique_channels']}")
            print(f"Total Duration:  {stats['total_duration_hours']} hours")
            return

        if args.search:
            results = extractor.search(args.search)
            if not results:
                print("No results found.")
                return

            print(f"\n=== Search Results for '{args.search}' ===\n")
            for r in results:
                print(f"[{r['video_id']}] {r['title']}")
                print(f"  Channel: {r['channel']}")
                print(f"  ...{r['snippet']}...")
                print()
            return

        # Process videos
        videos_to_process = []

        if args.input_file:
            videos_to_process.extend(load_video_list(args.input_file))

        if args.video:
            videos_to_process.extend(args.video)

        # Check if we have videos to process
        has_videos = args.playlist or videos_to_process
        if not has_videos:
            parser.print_help()
            return

        # Handle folder/collection assignment
        course_db = None
        collection_id = None
        folder_name = None

        if not args.no_folder:
            course_db = CourseDatabase(args.db)

            if args.folder:
                folder_name = args.folder
                folder_slug = slugify(folder_name)
            else:
                # Prompt for folder name
                folder_name, folder_slug = prompt_for_folder(course_db)

            # Check if collection exists or create new one
            existing = course_db.get_collection(folder_slug)
            if existing:
                collection_id = existing.id
                print(f"\nAdding to existing folder: {existing.name}")
            else:
                new_collection = Collection(
                    name=folder_name,
                    slug=folder_slug,
                    description=f"Extractions for {folder_name}",
                    collection_type=CollectionType.CUSTOM,
                )
                collection_id = course_db.create_collection(new_collection)
                print(f"\nCreated new folder: {folder_name}")

        # Process the videos
        if args.playlist:
            print(f"\nProcessing playlist: {args.playlist}")
            logger.info(f"Processing playlist: {args.playlist}")
            try:
                results = extractor.process_playlist(
                    args.playlist,
                    skip_existing=not args.no_skip,
                    on_progress=print_progress
                )
            except PlaylistError as e:
                logger.error(f"Failed to process playlist: {e}")
                print(f"\nError: {e}")
                sys.exit(1)
        else:
            print(f"\nProcessing {len(videos_to_process)} video(s)...")
            logger.info(f"Processing {len(videos_to_process)} videos")
            results = extractor.process_videos(
                videos_to_process,
                skip_existing=not args.no_skip,
                on_progress=print_progress
            )

        # Associate successful videos with the collection
        if collection_id and course_db:
            successful_ids = [r.video_id for r in results if r.success]
            for video_id in successful_ids:
                course_db.add_video_to_collection(collection_id, video_id)
            if successful_ids:
                print(f"\nAdded {len(successful_ids)} video(s) to folder: {folder_name}")
            course_db.close()

        # Summary
        print("\n=== Summary ===")
        successful = sum(1 for r in results if r.success)
        with_transcript = sum(1 for r in results if r.has_transcript)
        failed = [r for r in results if not r.success]

        print(f"Processed: {successful}/{len(results)}")
        print(f"With transcripts: {with_transcript}")
        if folder_name:
            print(f"Folder: {folder_name}")

        if failed:
            print(f"\nFailed ({len(failed)}):")
            for r in failed:
                print(f"  {r.video_id}: {r.error}")

        logger.info(f"Completed: {successful}/{len(results)} successful, {with_transcript} with transcripts")

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        print("\n\nInterrupted by user.")
        sys.exit(130)

    except TranscriptExtractorError as e:
        logger.error(f"Extraction error: {e}")
        print(f"\nError: {e}")
        sys.exit(1)

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        print(f"\nUnexpected error: {e}")
        sys.exit(1)

    finally:
        extractor.close()
        logger.debug("Cleanup complete")


if __name__ == '__main__':
    main()
