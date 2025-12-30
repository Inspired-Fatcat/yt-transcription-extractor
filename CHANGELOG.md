# Changelog

All notable changes to the YT Transcription Extractor project.

---

## [2025-12-30]

### Fixed
- **Updated youtube-transcript-api compatibility** for v1.2.3
  - Changed `TooManyRequests` exception to `RequestBlocked, IpBlocked` in `src/transcript.py`
  - Updated `requirements.txt` to use `>=1.0.0` instead of pinned `0.6.2`

---

## [2025-12-20]

### Added
- **Folder Organization System**: Extractions now prompt for a folder name to organize content by niche/topic
  - Interactive prompt shows existing folders and asks for folder name when starting extraction
  - New `--folder` / `-f` argument to specify folder via command line
  - New `--no-folder` argument to skip folder organization
  - Integrates with the existing collections system in `course_builder`
  - Videos are automatically associated with the selected folder/collection

### Fixed
- **Upgraded youtube-transcript-api from 0.6.2 to 1.2.3**
  - Updated `src/transcript.py` for new API syntax (v1.x breaking changes)
  - Changed from class methods to instance methods: `YouTubeTranscriptApi()`
  - Changed `list_transcripts()` → `list()`
  - Changed dict access to attribute access for transcript snippets (`item['text']` → `item.text`)

### Usage Examples
```bash
# Interactive - prompts for folder name
python main.py videos.txt

# Specify folder via command line
python main.py videos.txt -f "AI Development"
python main.py --playlist URL -f "Machine Learning Course"

# Skip folder organization
python main.py videos.txt --no-folder
```

### Collections Created
- `semantic-seo-koray-tukberg` - Semantic SEO content from Koray Tuğberk (87 videos in playlist)

### Extraction Progress - COMPLETED
- **Playlist**: `PL_g9rk58kWqRcnvxdNQMItSRukILNXx_I` (Koray's Semantic SEO Course)
- **Total videos**: 88 (unique in database)
- **Extracted with transcripts**: 88 (100%)
- **Status**: COMPLETE

---

## [2025-12-21]

### Fixed
- **Extracted 13 missing videos** from Koray's playlist
  - Original extraction missed early lectures (1-10, 19) due to initial rate limiting
  - Used VPN (South Africa) to bypass IP ban
  - All 88 videos now have transcripts

### VPN Region Testing
| Region | Status |
|--------|--------|
| Australia | Works |
| South Africa | Works |
| Mexico | Blocked |
| US/UK/Germany | Usually blocked |

### Updated Export
- `data/exports/semantic-seo-koray-tukberg/semantic_seo_koray_tukberg.json` - All 88 videos (2.90 MB)
- `data/exports/semantic-seo-koray-tukberg/koray_new_13_videos.json` - Just the 13 new extractions (326 KB)

### Project Restructuring
Reorganized the entire project for better maintainability:

**New folder structure:**
- `docs/` - All documentation (README.md, CHANGELOG.md, CLAUDE.md)
- `data/` - Database and exports
  - `data/transcripts.db` - SQLite database
  - `data/exports/<collection>/` - Exports organized by collection
  - `data/logs/` - Log files with rotation
  - `data/batch_state/` - Batch checkpoint files
- `scripts/` - Utility scripts
  - `scripts/samples/videos.txt` - Example video list
- `_archive/` - Archived/legacy files
  - `_archive/chroma_data/` - Vector embeddings (not actively used)
  - `_archive/transcripts/` - Loose transcript text files

**Files moved:**
- `transcripts.db` → `data/transcripts.db`
- `exports/` → `data/exports/`
- `README.md` → `docs/README.md`
- `CHANGELOG.md` → `docs/CHANGELOG.md`
- `CLAUDE.md` → `docs/CLAUDE.md`
- `extract_batch_with_cookies.py` → ~~`scripts/extract_batch.py`~~ → deleted (replaced by `batch.py`)
- `extract_with_retry.py` → ~~`scripts/extract_retry.py`~~ → deleted (replaced by `batch.py`)
- `videos.txt` → `scripts/samples/videos.txt`

### Scripts Added (now replaced by batch.py)
- ~~`scripts/extract_retry.py`~~ - Replaced by `batch.py` in later refactoring
- ~~`scripts/extract_batch.py`~~ - Replaced by `batch.py` in later refactoring

### Rate Limiting Research & Findings

#### What Causes Bans
- YouTube monitors request frequency per IP
- Rapid requests (< 5 sec apart) trigger bot detection
- Cloud provider IPs (AWS, GCP, Azure) are often pre-blocked
- Popular VPN server IPs may also be blocked

#### Delay Guidelines (Tested)
| Delay | Result |
|-------|--------|
| 1 second | Banned after ~20 requests |
| 5 seconds | Banned after ~50-100 requests |
| 10-30 seconds | May get banned on large batches |
| **60 seconds** | Safe for bulk extraction |

#### Solutions Implemented
1. **Adaptive delays** - starts at 3s, increases on rate limit, max 60s
2. **Batch processing** - 10 videos per batch with 2-min pauses between
3. **Browser cookies** - uses Firefox logged-in session for authentication
4. **1-minute delay** - the sweet spot that avoids all rate limiting

#### Recovery from IP Ban
- Bans typically lift after 30-60 minutes
- Or use VPN with less common server location (Australia worked)
- Avoid major VPN locations (US, UK, Germany often blocked)

### Usage for Future Extractions
```bash
# Safe extraction with 1-min delays (recommended)
python batch.py process videos.txt --folder "My Videos"

# Or use main.py with playlist
python main.py --playlist "PLAYLIST_URL" -f "Folder Name" --delay 60
```

---

## [2025-12-21] - Major Code Quality Refactoring

### Overview
Comprehensive refactoring to transform the codebase into a production-grade system with proper error handling, logging, resilience, and maintainability.

### Phase 1: Logging & Exception Handling

**New Files:**
- `src/exceptions.py` - Custom exception hierarchy
  - `TranscriptExtractorError` (base)
  - `ExtractionError`, `TranscriptNotFoundError`, `VideoNotFoundError`, `RateLimitError`
  - `DatabaseError`, `DatabaseConnectionError`, `DatabaseIntegrityError`
  - `ValidationError`, `InvalidVideoIdError`, `InvalidUrlError`
  - `ConfigurationError`, `MissingConfigError`

- `src/logging_config.py` - Structured logging with file rotation
  - Colored console output
  - JSON formatter option for production
  - Rotating file handler (10MB, 5 backups)

**Modified Files:**
- `src/transcript.py` - Replaced bare `except:` blocks with specific exceptions
- `src/extractor.py` - Added logging throughout, proper exception handling
- `main.py` - Added `--verbose` and `--log-file` options, proper error handling

### Phase 2: Database Reliability

**Changes to `src/database.py`:**
- Added context manager support (`with` statement)
- Enabled foreign key constraints
- Added transaction context manager for atomic operations
- Added `save_video_with_transcript()` for atomic saves
- Added CRUD operations: `update_video()`, `delete_video()`, `delete_transcript()`
- Added `ON DELETE CASCADE` for proper referential integrity

**Changes to `course_builder/core/database.py`:**
- Same context manager and transaction patterns
- Fixed `save_duplicate_group()` to be atomic
- Added `update_lesson()`, `update_collection()`, `delete_chunk()`
- Optimized `get_all_collections()` to single JOIN query
- Optimized `get_collection_stats()` from 5 queries to 1

### Phase 3: Configuration & Resilience

**New Files:**
- `config.yaml` - Unified configuration file
  - Database settings
  - Extraction settings (delays, retries, timeouts)
  - Batch processing settings
  - Logging settings
  - Rate limiting patterns

- `src/config.py` - Configuration loader with dataclasses
  - Loads from config.yaml
  - Environment variable overrides (YTE_SECTION__KEY)
  - Type-safe configuration objects

- `src/retry.py` - Retry decorator with exponential backoff
  - `@with_retry()` decorator for functions
  - `RetryContext` for imperative retry loops
  - Configurable backoff, jitter, retryable exceptions

**Modified Files:**
- `src/video_info.py` - Added timeout, retry, validation
  - VideoMetadata validation in `__post_init__`
  - Automatic retry on rate limit
  - Rate limit detection from error messages

### Phase 4: Unified Batch Processing

**New Files:**
- `src/batch_processor.py` - Unified batch processor
  - Checkpoint/resume support (JSON state files)
  - Graceful shutdown on SIGINT/SIGTERM
  - Progress callbacks
  - Failed video tracking
  - Configurable rate limiting

- `batch.py` - New CLI entry point
  ```bash
  python batch.py process videos.txt --folder "My Videos"
  python batch.py resume                    # Resume latest
  python batch.py resume batch_12345        # Resume specific
  python batch.py status                    # Show batch status
  python batch.py retry-failed              # Retry failed videos
  python batch.py list                      # List all batches
  python batch.py cleanup                   # Remove old state files
  ```

**Deleted Files:**
- `scripts/extract_batch.py` - Replaced by batch.py
- `scripts/extract_retry.py` - Replaced by batch.py

### Phase 5: Data Validation

- Added `__post_init__` validation to:
  - `VideoMetadata` - video_id, title, duration validation
  - `TranscriptSegment` - start/duration validation
  - `Transcript` - video_id, language validation
  - `Chunk` - video_id format, time ranges, token_count, chunk_index
  - `Collection` - name required, slug format (lowercase, hyphens only)
  - `CollectionVideo` - collection_id positive, video_id format

### Phase 6: Query Optimization

- Added missing indexes for better query performance
- Optimized N+1 queries in collection operations
- Single JOIN queries with aggregates instead of multiple queries

### New CLI Options

**main.py:**
```bash
--verbose, -V     # Enable DEBUG level logging
--log-file PATH   # Write logs to file
```

**batch.py:**
```bash
process           # Process videos with checkpointing
resume            # Resume interrupted batch
retry-failed      # Retry failed videos
status            # Show batch status
list              # List all batches
cleanup           # Remove old state files
```

### Updated Project Structure

```
YT Transcription Extractor/
├── main.py                      # Main CLI entry point
├── batch.py                     # Batch processing CLI (NEW)
├── course_builder.py            # Collection management CLI
├── config.yaml                  # Unified configuration (NEW)
├── requirements.txt
│
├── docs/                        # Documentation
│   ├── README.md
│   ├── CHANGELOG.md
│   └── CLAUDE.md
│
├── data/                        # All data files
│   ├── transcripts.db
│   ├── exports/
│   ├── logs/                    # Log files (NEW)
│   └── batch_state/             # Batch checkpoints (NEW)
│
├── src/                         # Core extraction module
│   ├── __init__.py
│   ├── database.py              # Enhanced with context managers
│   ├── extractor.py             # Enhanced with logging
│   ├── transcript.py            # Enhanced with validation
│   ├── video_info.py            # Enhanced with retry/validation
│   ├── exceptions.py            # NEW: Custom exceptions
│   ├── logging_config.py        # NEW: Logging setup
│   ├── config.py                # NEW: Configuration loader
│   ├── retry.py                 # NEW: Retry decorator
│   └── batch_processor.py       # NEW: Batch processor
│
├── course_builder/              # Collection management module
└── _archive/                    # Archived/legacy files
```

### Breaking Changes

- Old `scripts/extract_batch.py` and `scripts/extract_retry.py` have been removed
- Use `batch.py` instead for batch processing
- Database operations now require proper exception handling

### Migration Notes

If upgrading from a previous version:
1. Install pyyaml: `pip install pyyaml`
2. Review `config.yaml` and adjust settings
3. Use `batch.py` instead of old scripts
4. Add `--verbose` flag for debugging

### Summary

All 6 phases of the refactoring plan are complete:
- Phase 1: Logging & Exception Handling
- Phase 2: Database Reliability (context managers, transactions)
- Phase 3: Configuration & Resilience (config.yaml, retry decorator)
- Phase 4: Unified Batch Processing (checkpoint/resume)
- Phase 5: Data Validation (all dataclasses validated)
- Phase 6: Query Optimization (N+1 fixes, indexes)

The codebase is now production-grade with proper error handling, logging, resilience, and maintainability.
