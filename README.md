# YouTube Transcription Extractor

A tool to extract and organize YouTube video transcripts into a searchable SQLite database. Built for content creators, researchers, and knowledge workers.

## Features

- **Bulk Extraction** - Extract transcripts from videos, playlists, or video lists
- **Folder Organization** - Organize content into collections by topic
- **Full-Text Search** - Search across all transcripts instantly
- **Rate Limit Handling** - Built-in delays and retry logic
- **Batch Processing** - Checkpoint/resume support for large jobs

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Extract a single video
python main.py --video "https://youtube.com/watch?v=VIDEO_ID" -f "My Collection"

# Extract a playlist (with safe delays)
python main.py --playlist "https://youtube.com/playlist?list=PLAYLIST_ID" -f "Course" --delay 60

# Extract from a file (one URL per line)
python main.py videos.txt -f "Research"

# Search transcripts
python main.py --search "machine learning"

# View stats
python main.py --stats
```

## Command-Line Options

| Option | Description |
|--------|-------------|
| `--video, -v URL` | Process a single video |
| `--playlist, -p URL` | Process all videos from a playlist |
| `--folder, -f NAME` | Folder name to organize extractions |
| `--delay SECONDS` | Delay between requests (default: 1, recommended: 60) |
| `--search QUERY` | Search all transcripts |
| `--stats` | Show database statistics |

## Rate Limiting

YouTube rate-limits transcript requests aggressively. **Always use `--delay 60` for bulk extraction.**

| Delay | Result |
|-------|--------|
| 1 second | Banned after ~20 videos |
| 60 seconds | Safe for unlimited extraction |

If rate-limited, wait 30-60 minutes or use a VPN.

## Batch Processing

For large jobs with checkpoint/resume support:

```bash
# Start batch processing
python batch.py process --playlist "URL" -f "Folder"

# Resume interrupted batch
python batch.py resume

# Check status
python batch.py status
```

## Project Structure

```
├── main.py              # Main CLI
├── batch.py             # Batch processing CLI
├── course_builder.py    # Collection management
├── config.yaml          # Configuration
├── src/                 # Core extraction module
├── course_builder/      # Collection management module
├── data/                # Database and exports
└── docs/                # Full documentation
```

## Documentation

See [docs/README.md](docs/README.md) for complete documentation including:
- Detailed usage guide
- Database schema and queries
- Troubleshooting guide
- Export examples

## License

MIT License
