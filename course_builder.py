#!/usr/bin/env python3
"""
Knowledge Organizer CLI

Organize YouTube transcripts into searchable collections (folders).

Usage:
    python course_builder.py collection create "IndyDevDan" --type creator
    python course_builder.py collection add indydevdan VIDEO_ID
    python course_builder.py collection list
    python course_builder.py search "query" --collection indydevdan
    python course_builder.py process --all
"""

import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from course_builder.config import load_config
from course_builder.core.service import CourseBuilderService
from course_builder.models import CollectionType


def print_progress(current: int, total: int, video_id: str, status: str):
    """Print progress to console."""
    print(f"[{current}/{total}] {video_id}: {status}")


# ==================== COLLECTION COMMANDS ====================

def cmd_collection(args, service: CourseBuilderService):
    """Handle collection subcommands."""
    if args.collection_cmd == 'create':
        # Parse collection type
        ctype = CollectionType.CUSTOM
        if args.type:
            try:
                ctype = CollectionType(args.type)
            except ValueError:
                print(f"Invalid type. Options: {[t.value for t in CollectionType]}")
                return

        collection = service.create_collection(
            name=args.name,
            description=args.description or "",
            collection_type=ctype
        )
        print(f"Created collection: {collection.name} (slug: {collection.slug})")

    elif args.collection_cmd == 'list':
        collections = service.list_collections()
        if not collections:
            print("No collections found. Create one with: collection create \"Name\"")
            return

        print(f"\n=== Collections ({len(collections)}) ===\n")
        for c in collections:
            print(f"[{c.slug}] {c.name}")
            print(f"  Type: {c.collection_type.value} | Videos: {c.video_count} | Chunks: {c.chunk_count}")
            if c.description:
                print(f"  {c.description[:60]}...")
            print()

    elif args.collection_cmd == 'show':
        collection = service.get_collection(args.slug)
        if not collection:
            print(f"Collection not found: {args.slug}")
            return

        stats = service.get_collection_stats(args.slug)
        videos = service.get_collection_videos(args.slug)

        print(f"\n=== {collection.name} ===")
        print(f"Slug: {collection.slug}")
        print(f"Type: {collection.collection_type.value}")
        print(f"Description: {collection.description or '(none)'}")
        print(f"\nStats:")
        print(f"  Videos: {stats['video_count']}")
        print(f"  Chunks: {stats['chunk_count']}")
        print(f"  Topics: {stats['topic_count']}")
        print(f"  Duration: {stats['duration_hours']:.1f} hours")

        if videos:
            print(f"\nVideos:")
            for v in videos:
                dur = v['duration'] // 60 if v['duration'] else 0
                print(f"  [{v['video_id']}] {v['title'][:50]}... ({dur} min)")

    elif args.collection_cmd == 'add':
        if service.add_video_to_collection(args.slug, args.video_id, args.notes or ""):
            print(f"Added {args.video_id} to collection '{args.slug}'")
        else:
            print(f"Collection not found: {args.slug}")

    elif args.collection_cmd == 'remove':
        if service.remove_video_from_collection(args.slug, args.video_id):
            print(f"Removed {args.video_id} from collection '{args.slug}'")
        else:
            print(f"Collection not found: {args.slug}")

    elif args.collection_cmd == 'delete':
        if service.delete_collection(args.slug):
            print(f"Deleted collection: {args.slug}")
        else:
            print(f"Collection not found: {args.slug}")


# ==================== PROCESS COMMANDS ====================

def cmd_process(args, service: CourseBuilderService):
    """Process videos: chunk and embed."""
    if args.video:
        # Process single video
        print(f"Processing video: {args.video}")

        def progress(status: str):
            print(f"  {status}")

        result = service.process_video(args.video, on_progress=progress)

        if result['error']:
            print(f"  Error: {result['error']}")
        else:
            print(f"  Chunks: {result['chunks_created']}")
            print(f"  Embeddings: {result['embeddings_created']}")

    elif args.all:
        # Process all videos
        print("Processing all videos...")
        results = service.process_all_videos(
            skip_processed=not args.reprocess,
            on_progress=print_progress
        )

        # Summary
        print("\n=== Summary ===")
        successful = [r for r in results if not r['error']]
        failed = [r for r in results if r['error']]

        total_chunks = sum(r['chunks_created'] for r in successful)
        total_embeddings = sum(r['embeddings_created'] for r in successful)

        print(f"Processed: {len(successful)}/{len(results)} videos")
        print(f"Total chunks: {total_chunks}")
        print(f"Total embeddings: {total_embeddings}")

        if failed:
            print(f"\nFailed ({len(failed)}):")
            for r in failed:
                print(f"  {r['video_id']}: {r['error']}")
    else:
        print("Specify --video VIDEO_ID or --all")


# ==================== TOPIC COMMANDS ====================

def cmd_topics(args, service: CourseBuilderService):
    """Handle topic subcommands."""
    if args.topics_cmd == 'extract':
        # Extract topics
        collection = args.collection if hasattr(args, 'collection') else None

        if collection:
            print(f"Extracting topics from collection '{collection}'...")
        else:
            print("Extracting topics from all chunks...")

        def progress(current: int, total: int, chunk_id: str, status: str):
            print(f"[{current}/{total}] Chunk {chunk_id}: {status}")

        results = service.extract_all_topics(
            skip_extracted=not args.reextract,
            collection_slug=collection,
            on_progress=progress
        )

        if not results:
            print("No chunks to process (all already extracted).")
            return

        # Summary
        successful = [r for r in results if not r.get('error')]
        failed = [r for r in results if r.get('error')]
        total_topics = sum(r.get('topics_count', 0) for r in successful)

        print(f"\n=== Summary ===")
        print(f"Processed: {len(successful)}/{len(results)} chunks")
        print(f"Total topics extracted: {total_topics}")

        if failed:
            print(f"\nFailed ({len(failed)}):")
            for r in failed:
                print(f"  Chunk {r['chunk_id']}: {r['error']}")

    elif args.topics_cmd == 'list':
        # List topics
        collection = args.collection if hasattr(args, 'collection') else None

        if collection:
            topics = service.get_topics_for_collection(collection)
            print(f"\n=== Topics in '{collection}' ({len(topics)}) ===\n")
        else:
            topics = service.get_all_topics()
            print(f"\n=== All Topics ({len(topics)}) ===\n")

        if not topics:
            print("No topics found. Run 'topics extract' first.")
            return

        # Group by category
        by_category = {}
        for t in topics:
            cat = t.category.value
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(t)

        for category, cat_topics in sorted(by_category.items()):
            print(f"[{category.upper()}]")
            for t in sorted(cat_topics, key=lambda x: -x.mention_count)[:10]:
                print(f"  • {t.name} ({t.mention_count} mentions)")
            if len(cat_topics) > 10:
                print(f"  ... and {len(cat_topics) - 10} more")
            print()

    elif args.topics_cmd == 'show':
        # Show details for a topic
        topic = service.db.get_topic_by_name(args.name)
        if not topic:
            print(f"Topic not found: {args.name}")
            return

        print(f"\n=== {topic.name} ===")
        print(f"Category: {topic.category.value}")
        print(f"Description: {topic.description}")
        print(f"Confidence: {topic.confidence:.2f}")
        print(f"Mentions: {topic.mention_count}")

        # Show chunks containing this topic
        chunk_links = service.db.get_chunks_for_topic(topic.id)
        if chunk_links:
            print(f"\nFound in {len(chunk_links)} chunks:")
            for chunk, relevance in chunk_links[:5]:
                meta = service.db.get_chunk_metadata(chunk.id)
                theme = meta['main_theme'] if meta else "Unknown"
                print(f"  [{relevance:.0%}] {theme}")
                print(f"      {chunk.text[:100]}...")


# ==================== DEDUPE COMMANDS ====================

def cmd_dedupe(args, service: CourseBuilderService):
    """Handle deduplication subcommands."""
    if args.dedupe_cmd == 'find':
        # Find duplicates
        collection = args.collection if hasattr(args, 'collection') else None
        threshold = args.threshold if hasattr(args, 'threshold') else None

        if collection:
            print(f"Finding duplicates in collection '{collection}'...")
        else:
            print("Finding duplicates across all chunks...")

        def progress(status: str):
            print(f"  {status}")

        clusters = service.find_duplicates(
            collection_slug=collection,
            threshold=threshold,
            on_progress=progress,
        )

        if not clusters:
            print("\nNo duplicates found.")
            return

        print(f"\n=== Found {len(clusters)} Duplicate Clusters ===\n")
        for i, cluster in enumerate(clusters, 1):
            print(f"Cluster {i} ({cluster['size']} chunks):")
            for chunk in cluster['chunks']:
                print(f"  [{chunk['similarity']:.0%}] {chunk['video_title']}")
                print(f"      Time: {chunk['timestamp']} | Chunk {chunk['chunk_id']}")
                print(f"      {chunk['text_preview'][:80]}...")
            print()

        if args.save:
            count = service.save_duplicate_groups(clusters)
            print(f"Saved {count} duplicate groups to database.")

    elif args.dedupe_cmd == 'list':
        # List saved duplicate groups
        groups = service.get_duplicate_groups()

        if not groups:
            print("No duplicate groups saved. Run 'dedupe find --save' first.")
            return

        print(f"\n=== Saved Duplicate Groups ({len(groups)}) ===\n")
        for group in groups:
            print(f"Group {group['id']} ({len(group['members'])} members):")
            for member in group['members']:
                print(f"  [{member['similarity']:.0%}] {member['video_title']} @ {member['timestamp']}")
            if group['merged_content']:
                print(f"  Merged: {group['merged_content'][:100]}...")
            print()


# ==================== SEARCH COMMANDS ====================

def cmd_search(args, service: CourseBuilderService):
    """Semantic search across transcripts."""
    query = ' '.join(args.query)

    if args.collection:
        print(f"Searching in collection '{args.collection}' for: '{query}'\n")
        results = service.search_in_collection(args.collection, query, limit=args.limit)
        if results is None:
            print(f"Collection not found: {args.collection}")
            return
    else:
        print(f"Searching all collections for: '{query}'\n")
        results = service.semantic_search(query, limit=args.limit)

    if not results:
        print("No results found.")
        return

    for i, r in enumerate(results, 1):
        print(f"{i}. [{r['similarity']:.0%}] {r['video_title']}")
        print(f"   Channel: {r['channel']} | Time: {r['timestamp']}")
        print(f"   {r['text_preview']}")
        print()


# ==================== STATS & INFO ====================

def cmd_stats(args, service: CourseBuilderService):
    """Show statistics."""
    stats = service.get_stats()

    print("\n=== Knowledge Organizer Statistics ===")
    print(f"Collections:           {stats['collection_count']}")
    print(f"Videos in database:    {stats['video_count']}")
    print(f"Videos chunked:        {stats['videos_chunked']}")
    print(f"Total chunks:          {stats['chunk_count']}")
    print(f"Total embeddings:      {stats['embedding_count']}")
    print(f"Topics extracted:      {stats['topic_count']}")

    if not stats['embeddings_synced']:
        print(f"\n  Warning: Embeddings not synced with chunks")
        print(f"  Run 'process --all' to generate missing embeddings")


def cmd_videos(args, service: CourseBuilderService):
    """List all videos."""
    videos = service.get_all_videos()

    if not videos:
        print("No videos found.")
        return

    print(f"\n=== Videos ({len(videos)}) ===\n")
    for v in videos:
        duration_mins = v['duration'] // 60 if v['duration'] else 0
        print(f"[{v['video_id']}] {v['title']}")
        print(f"  Channel: {v['channel']} | Duration: {duration_mins} min")

        # Show collections for this video
        collections = service.db.get_collections_for_video(v['video_id'])
        if collections:
            coll_names = ', '.join(c.slug for c in collections)
            print(f"  Collections: {coll_names}")
        print()


def main():
    parser = argparse.ArgumentParser(
        description="Knowledge Organizer - Organize YouTube transcripts into searchable collections",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        '--config', '-c',
        default='config.yaml',
        help='Path to config file'
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Collection command with subcommands
    coll_parser = subparsers.add_parser('collection', help='Manage collections (folders)')
    coll_subparsers = coll_parser.add_subparsers(dest='collection_cmd')

    # collection create
    create_parser = coll_subparsers.add_parser('create', help='Create a new collection')
    create_parser.add_argument('name', help='Collection name')
    create_parser.add_argument('--description', '-d', help='Description')
    create_parser.add_argument('--type', '-t', choices=[t.value for t in CollectionType],
                               help='Collection type')

    # collection list
    coll_subparsers.add_parser('list', help='List all collections')

    # collection show
    show_parser = coll_subparsers.add_parser('show', help='Show collection details')
    show_parser.add_argument('slug', help='Collection slug')

    # collection add
    add_parser = coll_subparsers.add_parser('add', help='Add video to collection')
    add_parser.add_argument('slug', help='Collection slug')
    add_parser.add_argument('video_id', help='Video ID to add')
    add_parser.add_argument('--notes', '-n', help='Notes about the video')

    # collection remove
    remove_parser = coll_subparsers.add_parser('remove', help='Remove video from collection')
    remove_parser.add_argument('slug', help='Collection slug')
    remove_parser.add_argument('video_id', help='Video ID to remove')

    # collection delete
    delete_parser = coll_subparsers.add_parser('delete', help='Delete a collection')
    delete_parser.add_argument('slug', help='Collection slug')

    # Process command
    process_parser = subparsers.add_parser('process', help='Process videos (chunk + embed)')
    process_parser.add_argument('--video', '-v', help='Process single video by ID')
    process_parser.add_argument('--all', '-a', action='store_true', help='Process all videos')
    process_parser.add_argument('--reprocess', action='store_true', help='Reprocess already chunked videos')

    # Topics command with subcommands
    topics_parser = subparsers.add_parser('topics', help='Extract and manage topics')
    topics_subparsers = topics_parser.add_subparsers(dest='topics_cmd')

    # topics extract
    extract_parser = topics_subparsers.add_parser('extract', help='Extract topics from chunks')
    extract_parser.add_argument('--collection', '-c', help='Only process this collection')
    extract_parser.add_argument('--reextract', action='store_true', help='Re-extract already processed chunks')

    # topics list
    list_topics_parser = topics_subparsers.add_parser('list', help='List extracted topics')
    list_topics_parser.add_argument('--collection', '-c', help='Show topics for this collection')

    # topics show
    show_topic_parser = topics_subparsers.add_parser('show', help='Show topic details')
    show_topic_parser.add_argument('name', help='Topic name')

    # Dedupe command with subcommands
    dedupe_parser = subparsers.add_parser('dedupe', help='Find and manage duplicate content')
    dedupe_subparsers = dedupe_parser.add_subparsers(dest='dedupe_cmd')

    # dedupe find
    find_parser = dedupe_subparsers.add_parser('find', help='Find duplicate chunks')
    find_parser.add_argument('--collection', '-c', help='Only search in this collection')
    find_parser.add_argument('--threshold', '-t', type=float, help='Similarity threshold (0.0-1.0)')
    find_parser.add_argument('--save', '-s', action='store_true', help='Save found duplicates to database')

    # dedupe list
    dedupe_subparsers.add_parser('list', help='List saved duplicate groups')

    # Search command
    search_parser = subparsers.add_parser('search', help='Semantic search')
    search_parser.add_argument('query', nargs='+', help='Search query')
    search_parser.add_argument('--collection', '-c', help='Search only in this collection')
    search_parser.add_argument('--limit', '-n', type=int, default=10, help='Number of results')

    # Stats command
    subparsers.add_parser('stats', help='Show statistics')

    # Videos command
    subparsers.add_parser('videos', help='List all videos')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Load config and initialize service
    try:
        config = load_config(args.config if Path(args.config).exists() else None)
        service = CourseBuilderService(config=config)
    except ValueError as e:
        print(f"Configuration error: {e}")
        print("\nMake sure you have set the required environment variables:")
        print("  OPENAI_API_KEY - for generating embeddings")
        sys.exit(1)

    try:
        if args.command == 'collection':
            if not args.collection_cmd:
                # Show collection help
                print("Usage: collection {create,list,show,add,remove,delete}")
                return
            cmd_collection(args, service)
        elif args.command == 'process':
            cmd_process(args, service)
        elif args.command == 'topics':
            if not args.topics_cmd:
                print("Usage: topics {extract,list,show}")
                return
            cmd_topics(args, service)
        elif args.command == 'dedupe':
            if not args.dedupe_cmd:
                print("Usage: dedupe {find,list}")
                return
            cmd_dedupe(args, service)
        elif args.command == 'search':
            cmd_search(args, service)
        elif args.command == 'stats':
            cmd_stats(args, service)
        elif args.command == 'videos':
            cmd_videos(args, service)
    finally:
        service.close()


if __name__ == '__main__':
    main()
