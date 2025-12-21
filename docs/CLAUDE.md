# Claude Code Context

This file provides context for Claude Code when working on this project.

## Project Overview

**YT Transcription Extractor** is a YouTube transcript extraction and organization tool. It extracts transcripts from YouTube videos/playlists, stores them in a SQLite database organized by folders (collections), and provides full-text search.

## Architecture

### Core System

1. **Extraction** (`main.py`, `src/`)
   - Extracts video metadata and transcripts from YouTube
   - Stores in SQLite database
   - Organizes into folders/collections
   - Full-text search capabilities

2. **Folder Management** (`course_builder.py`, `course_builder/`)
   - Create and manage collections (folders)
   - View folder contents and stats
   - Add/remove videos from folders

## Key Files

| File | Purpose |
|------|---------|
| `main.py` | CLI entry point for extraction |
| `batch.py` | Batch processing CLI with checkpoint/resume |
| `course_builder.py` | CLI for folder/collection management |
| `config.yaml` | Unified configuration file |
| `src/extractor.py` | Main extraction orchestrator |
| `src/transcript.py` | YouTube transcript API wrapper |
| `src/database.py` | SQLite operations with context managers |
| `src/exceptions.py` | Custom exception hierarchy |
| `src/logging_config.py` | Structured logging setup |
| `src/config.py` | Configuration loader |
| `src/retry.py` | Retry decorator with exponential backoff |
| `src/batch_processor.py` | Batch processor with checkpoints |
| `course_builder/core/database.py` | Extended database for collections |
| `data/transcripts.db` | SQLite database |
| `data/exports/` | Exported JSON files by collection |
| `data/logs/` | Log files with rotation |
| `data/batch_state/` | Batch checkpoint files |

## Database Schema

**Main tables:**
- `videos` - Video metadata (title, channel, duration, etc.)
- `transcripts` - Full transcript text + segments JSON
- `collections` - Folders for organizing content
- `collection_videos` - Many-to-many video-collection links

## Common Tasks

### Extract from Playlist
```bash
# With 60-second delays to avoid rate limiting (IMPORTANT!)
python main.py --playlist "PLAYLIST_URL" -f "Folder Name" --delay 60

# Or use batch CLI (recommended for large playlists)
python batch.py process --playlist "PLAYLIST_URL" -f "Folder Name"
```

### Batch Processing with Checkpoints
```bash
# Process videos with checkpoint/resume support
python batch.py process videos.txt --folder "My Videos"

# Resume interrupted batch
python batch.py resume

# Retry failed videos
python batch.py retry-failed

# Check status
python batch.py status
python batch.py list
```

### Manage Folders
```bash
python course_builder.py collection list
python course_builder.py collection show <slug>
python course_builder.py collection create "Name"
```

### Search Transcripts
```bash
python main.py --search "query"
```

### Export Transcript to File
```bash
# See README.md for export script
```

## Rate Limiting (IMPORTANT)

YouTube aggressively rate-limits transcript requests:

| Delay | Safe for |
|-------|----------|
| 1 sec | ~20 videos then banned |
| 60 sec | Unlimited (tested with 88 videos) |

**If banned:**
1. Wait 30-60 minutes, OR
2. Use VPN with a less common region

### VPN Regions That Work
| Region | Status |
|--------|--------|
| Australia | Works |
| South Africa | Works |
| Mexico | Blocked |
| US/UK/Germany | Usually blocked (popular VPN locations) |

**Tip:** Less common VPN regions have fresher IPs that aren't blocked yet.

## Dependencies

- `youtube-transcript-api` v1.2.3 - Transcript extraction
- `yt-dlp` - Video metadata
- `requests` - HTTP client
- `pyyaml` - Configuration file parsing (optional but recommended)

## Code Patterns

### Database Access (with Context Managers)
```python
from src.database import TranscriptDatabase
from course_builder.core.database import CourseDatabase

# Use context managers for automatic cleanup
with TranscriptDatabase('data/transcripts.db') as db:
    db.save_video(metadata)
    db.save_transcript(transcript)

# Atomic operations with transactions
with db.transaction():
    db.save_video(metadata)
    db.save_transcript(transcript)  # Rolls back if this fails

# Collection operations
with CourseDatabase('data/transcripts.db') as cdb:
    cdb.create_collection(collection)
    cdb.add_video_to_collection(collection_id, video_id)
```

### Exception Handling
```python
from src.exceptions import (
    RateLimitError,
    VideoNotFoundError,
    TranscriptNotFoundError,
    DatabaseError,
)

try:
    transcript = get_transcript(video_id, raise_on_error=True)
except RateLimitError as e:
    print(f"Rate limited, retry after {e.retry_after}s")
except TranscriptNotFoundError as e:
    print(f"No transcript: {e.available_languages}")
```

### Retry with Backoff
```python
from src.retry import with_retry, RetryContext

# Decorator approach
@with_retry(max_attempts=3, backoff_factor=2.0)
def fetch_data():
    ...

# Context manager approach
retry = RetryContext(max_attempts=3)
while retry.should_retry():
    try:
        result = do_something()
        retry.record_success()
        break
    except RateLimitError as e:
        retry.record_failure(e)
```

### Configuration
```python
from src.config import get_config

config = get_config()
delay = config.extraction.delay_between_requests
db_path = config.database.path
```

### Logging
```python
from src.logging_config import setup_logging, get_logger

# Initialize at startup
setup_logging(level="DEBUG", log_file="data/logs/app.log")

# Get module logger
logger = get_logger('my_module')
logger.info("Processing video")
logger.error("Failed", exc_info=True)
```

### Transcript API (v1.2.3)
```python
# Must instantiate API first
api = YouTubeTranscriptApi()
transcript_list = api.list(video_id)
transcript = transcript_list.find_generated_transcript(['en'])
data = transcript.fetch()

# Access segments via attributes, not dict
for segment in data:
    text = segment.text      # NOT segment['text']
    start = segment.start
    duration = segment.duration
```

## Project Structure

```
YT Transcription Extractor/
├── main.py                      # Main CLI
├── batch.py                     # Batch processing CLI
├── course_builder.py            # Collection management CLI
├── config.yaml                  # Unified configuration
│
├── docs/                        # Documentation
│   ├── README.md
│   ├── CHANGELOG.md
│   └── CLAUDE.md
│
├── data/                        # All data files
│   ├── transcripts.db
│   ├── exports/<collection>/
│   ├── logs/                    # Log files
│   └── batch_state/             # Batch checkpoints
│
├── src/                         # Core extraction module
│   ├── database.py              # With context managers
│   ├── extractor.py             # With logging
│   ├── transcript.py            # With validation
│   ├── video_info.py            # With retry
│   ├── exceptions.py            # Custom exceptions
│   ├── logging_config.py        # Logging setup
│   ├── config.py                # Configuration
│   ├── retry.py                 # Retry decorator
│   └── batch_processor.py       # Batch processing
│
├── course_builder/              # Collection management module
└── _archive/                    # Archived/legacy files
```

## Recent Changes

See `docs/CHANGELOG.md` for detailed history. Key updates:
- **Major refactoring** with proper error handling, logging, and resilience
- Custom exception hierarchy in `src/exceptions.py`
- Structured logging with rotation in `src/logging_config.py`
- Unified configuration in `config.yaml` and `src/config.py`
- Retry decorator with exponential backoff in `src/retry.py`
- Batch processing with checkpoint/resume in `batch.py`
- Context managers and transactions for database operations
- Data validation in VideoMetadata and Transcript classes
- Optimized database queries (N+1 fixes)
