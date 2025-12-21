# YouTube Transcription Extractor

A powerful tool to extract and organize YouTube video transcripts into folders. Built for content creators, researchers, and knowledge workers who want to build searchable transcript libraries organized by topic.

## Features

- **Bulk Extraction** - Extract transcripts from individual videos, playlists, or video lists
- **Folder Organization** - Organize content into folders/collections by topic or niche
- **Full-Text Search** - Search across all transcripts instantly
- **Rate Limit Handling** - Built-in delays and retry logic to avoid YouTube bans
- **Database Storage** - All data stored in SQLite for easy querying and portability

## Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd "YT Transcription Extractor"

# Install dependencies
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
```

### Bulk Extraction (Recommended for Large Playlists)

For large playlists (50+ videos), use the batch extraction script with 60-second delays:

```bash
# Option 1: Use main.py with delay
python main.py --playlist "PLAYLIST_URL" -f "Folder Name" --delay 60

# Option 2: Use batch script (better rate limit handling)
python scripts/extract_batch.py --all
```

## Folder Organization

When you start an extraction, you'll be prompted to enter a folder name. This organizes your content by topic/niche.

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
# List all folders
python course_builder.py collection list

# View folder details
python course_builder.py collection show semantic-seo

# Create a new folder
python course_builder.py collection create "New Folder"
```

## Rate Limiting

YouTube rate-limits transcript requests aggressively. Here's what we learned:

| Delay Between Requests | Result |
|------------------------|--------|
| 1 second | Banned after ~20 videos |
| 5 seconds | Banned after ~50-100 videos |
| **60 seconds** | Safe for unlimited extraction |

### Recommended: Always Use 60-Second Delays

```bash
python main.py --playlist "URL" -f "Folder" --delay 60
```

### If You Get Rate-Limited

1. **Wait** - Bans typically lift after 30-60 minutes
2. **Use VPN** - Connect to a less common location
3. **Use Cookies** - Log into YouTube in Firefox, then run batch extraction

```bash
# Rate-limit safe extraction with browser cookies
python scripts/extract_batch.py --all
```

### VPN Regions That Work

| Region | Status |
|--------|--------|
| Australia | Works |
| South Africa | Works |
| Mexico | Blocked |
| US/UK/Germany | Usually blocked (popular VPN locations) |

Less common VPN regions have fresher IPs that aren't blocked yet.

## Exporting Transcripts

Export a transcript to a text file:

```bash
# Quick export using Python
python -c "
from src.database import TranscriptDatabase
import json

db = TranscriptDatabase('data/transcripts.db')
cursor = db.conn.execute('''
    SELECT v.title, v.channel, t.segments_json
    FROM transcripts t
    JOIN videos v ON t.video_id = v.video_id
    WHERE t.video_id = 'VIDEO_ID'
''')
row = cursor.fetchone()
segments = json.loads(row[2])

with open('transcript.txt', 'w', encoding='utf-8') as f:
    f.write(f'Title: {row[0]}\nChannel: {row[1]}\n\n')
    for seg in segments:
        mins, secs = divmod(int(seg['start']), 60)
        f.write(f'[{mins:02d}:{secs:02d}] {seg[\"text\"]}\n')

print('Exported to transcript.txt')
"
```

## Project Structure

```
YT Transcription Extractor/
├── main.py                      # Main CLI entry point
├── course_builder.py            # Folder/collection management
├── requirements.txt             # Python dependencies
├── .env                         # Environment variables (API keys)
│
├── docs/                        # Documentation
│   ├── README.md               # This file
│   ├── CHANGELOG.md            # Development history
│   └── CLAUDE.md               # AI assistant context
│
├── data/                        # All data files
│   ├── transcripts.db          # SQLite database
│   └── exports/                # Exported JSON files
│       └── <collection-slug>/  # Organized by collection
│
├── src/                         # Core extraction module
│   ├── extractor.py            # Main extraction orchestrator
│   ├── transcript.py           # YouTube transcript API wrapper
│   ├── database.py             # Database operations
│   └── video_info.py           # Video metadata extraction
│
├── scripts/                     # Utility scripts
│   ├── extract_batch.py        # Rate-limit safe batch extraction
│   ├── extract_retry.py        # Adaptive retry extraction
│   └── samples/                # Example files
│       └── videos.txt          # Sample video list
│
├── course_builder/              # Collection/folder management
│   ├── core/
│   │   └── database.py         # Extended database operations
│   └── models/
│       └── collection.py       # Collection/folder model
│
└── _archive/                    # Archived/unused files
    ├── chroma_data/            # Vector embeddings (legacy)
    └── transcripts/            # Loose transcript files
```

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

## Dependencies

```
youtube-transcript-api>=1.2.3   # Transcript extraction
yt-dlp                          # Video metadata
requests                        # HTTP client
browser-cookie3                 # Cookie extraction (for rate limiting bypass)
```

## Troubleshooting

### "Subtitles are disabled for this video"
The video doesn't have captions. The video owner must enable them.

### "YouTube is blocking requests from your IP"
You've been rate-limited. Solutions:
1. Wait 30-60 minutes
2. Use a VPN (try Australia or Eastern Europe)
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
