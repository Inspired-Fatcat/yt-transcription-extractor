# YouTube Transcription Extractor

A powerful tool to extract and organize YouTube video transcripts into a searchable SQLite database. Built for content creators, researchers, and knowledge workers who want to build searchable transcript libraries organized by topic.

## Features

- **Bulk Extraction** - Extract transcripts from individual videos, playlists, or video lists
- **Folder Organization** - Organize content into folders/collections by topic or niche
- **Full-Text Search** - Search across all transcripts instantly
- **Rate Limit Handling** - Built-in delays and retry logic to avoid YouTube bans
- **Batch Processing** - Checkpoint/resume support for large jobs
- **Database Storage** - All data stored in SQLite for easy querying and portability

## Quick Start

### Installation

```bash
git clone https://github.com/KIKONUTINO/YT-Transcription-Extractor.git
cd YT-Transcription-Extractor
pip install -r requirements.txt
```

### Extract Your First Video

```bash
# Single video (will prompt for folder name)
python main.py --video "https://youtube.com/watch?v=VIDEO_ID"

# Single video with folder specified
python main.py --video "https://youtube.com/watch?v=VIDEO_ID" -f "My Collection"

# From a playlist (with safe 60-second delays)
python main.py --playlist "https://youtube.com/playlist?list=PLAYLIST_ID" -f "Course Name" --delay 60

# From a text file (one URL per line)
python main.py videos.txt -f "Research Videos"
```

### Search Transcripts

```bash
python main.py --search "machine learning"
```

### View Statistics

```bash
python main.py --stats
```

## Usage Guide

### Basic Commands

| Command | Description |
|---------|-------------|
| `python main.py videos.txt` | Extract from file (prompts for folder) |
| `python main.py --video URL` | Extract single video |
| `python main.py --playlist URL` | Extract entire playlist |
| `python main.py --search "query"` | Search all transcripts |
| `python main.py --stats` | Show database statistics |

### Command-Line Options

```
--video, -v URL       Process a single video (can be used multiple times)
--playlist, -p URL    Process all videos from a playlist
--folder, -f NAME     Folder name to organize extractions
--no-folder           Skip folder organization
--delay SECONDS       Delay between requests (default: 1, recommended: 60)
--language, -l LANG   Preferred transcript language (default: en)
--db PATH             Custom database path (default: data/transcripts.db)
--no-skip             Re-process videos already in database
--verbose, -V         Enable verbose output (DEBUG level logging)
--log-file PATH       Write logs to file
```

## Batch Processing

For large jobs with checkpoint/resume support:

```bash
# Start batch processing
python batch.py process --playlist "URL" -f "Folder"

# Process from file
python batch.py process videos.txt --folder "My Videos"

# Resume interrupted batch
python batch.py resume

# Retry failed videos
python batch.py retry-failed

# Check status
python batch.py status

# List all batches
python batch.py list
```

## Folder Organization

When you start an extraction, you'll be prompted to enter a folder name:

```
=== Existing Folders ===
  - ai-development (ai-development) - 15 videos
  - semantic-seo (semantic-seo) - 75 videos

Enter a folder name for these extractions.
(Use an existing name to add to that folder, or enter a new name)

Folder name: Machine Learning
```

### Managing Folders

```bash
python course_builder.py collection list
python course_builder.py collection show <slug>
python course_builder.py collection create "New Folder"
```

## Rate Limiting

YouTube rate-limits transcript requests aggressively:

| Delay | Result |
|-------|--------|
| 1 second | Banned after ~20 videos |
| 5 seconds | Banned after ~50-100 videos |
| **60 seconds** | Safe for unlimited extraction |

**Always use `--delay 60` for bulk extraction.**

### If You Get Rate-Limited

1. **Wait** - Bans typically lift after 30-60 minutes
2. **Use VPN** - Connect to a less common region (Australia, South Africa work well)
3. **Use longer delays** - Always use `--delay 60` for future extractions

## Database

All data is stored in `data/transcripts.db` (SQLite). Key tables:

| Table | Contents |
|-------|----------|
| `videos` | Video metadata (title, channel, duration, etc.) |
| `transcripts` | Full text + timestamped segments |
| `collections` | Folders for organization |
| `collection_videos` | Which videos are in which folders |

### Query Examples

```sql
-- Find all videos in a folder
SELECT v.title, v.channel
FROM videos v
JOIN collection_videos cv ON v.video_id = cv.video_id
JOIN collections c ON cv.collection_id = c.id
WHERE c.slug = 'semantic-seo';

-- Search transcripts
SELECT v.title, substr(t.full_text, 1, 200)
FROM transcripts t
JOIN videos v ON t.video_id = v.video_id
WHERE t.full_text LIKE '%your search term%';
```

## Project Structure

```
├── main.py              # Main CLI entry point
├── batch.py             # Batch processing CLI
├── course_builder.py    # Collection management CLI
├── config.yaml          # Configuration file
├── requirements.txt     # Python dependencies
├── CHANGELOG.md         # Version history
├── CLAUDE.md            # AI assistant context
│
├── src/                 # Core extraction module
│   ├── extractor.py     # Main extraction orchestrator
│   ├── transcript.py    # YouTube transcript API wrapper
│   ├── database.py      # SQLite operations
│   ├── video_info.py    # Video metadata extraction
│   ├── exceptions.py    # Custom exception hierarchy
│   ├── logging_config.py# Structured logging
│   ├── config.py        # Configuration loader
│   ├── retry.py         # Retry with backoff
│   └── batch_processor.py # Batch processor
│
├── course_builder/      # Collection management module
├── data/                # Database and exports
│   ├── transcripts.db   # SQLite database
│   └── exports/         # Exported JSON files
│
└── examples/            # Example files
    └── videos.txt       # Sample video list
```

## Dependencies

```
youtube-transcript-api   # Transcript extraction
yt-dlp                   # Video metadata
requests                 # HTTP client
pyyaml                   # Configuration parsing
```

## Troubleshooting

### "Subtitles are disabled for this video"
The video doesn't have captions. The video owner must enable them.

### "YouTube is blocking requests from your IP"
You've been rate-limited. Solutions:
1. Wait 30-60 minutes
2. Use a VPN (try Australia or South Africa)
3. Use `--delay 60` for all future extractions

### "No transcript available"
Try different languages:
```bash
python main.py --video URL -l es -l en  # Try Spanish first, then English
```

### Unicode errors on Windows
```bash
set PYTHONIOENCODING=utf-8
```

## License

MIT License
