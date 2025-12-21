"""Configuration management for Course Builder."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml
from dotenv import load_dotenv


@dataclass
class VectorStoreConfig:
    """ChromaDB configuration."""
    path: str = "chroma_data"
    collection_name: str = "transcript_chunks"


@dataclass
class EmbeddingConfig:
    """Embedding service configuration."""
    provider: str = "openai"
    model: str = "text-embedding-3-small"
    batch_size: int = 100
    cache_embeddings: bool = True
    dimensions: int = 1536


@dataclass
class LLMConfig:
    """LLM configuration for Claude."""
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    temperature: float = 0.3


@dataclass
class ChunkingConfig:
    """Chunking strategy configuration."""
    target_duration_seconds: int = 150  # 2.5 minutes
    overlap_ratio: float = 0.15
    min_tokens: int = 100
    max_tokens: int = 600


@dataclass
class DeduplicationConfig:
    """Deduplication configuration."""
    similarity_threshold: float = 0.85
    min_cluster_size: int = 2


@dataclass
class Config:
    """Main configuration container."""
    database_path: str = "data/transcripts.db"
    vector_store: VectorStoreConfig = field(default_factory=VectorStoreConfig)
    embeddings: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    chunking: ChunkingConfig = field(default_factory=ChunkingConfig)
    deduplication: DeduplicationConfig = field(default_factory=DeduplicationConfig)

    # API keys (loaded from environment)
    anthropic_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None


def load_config(config_path: Optional[str] = None) -> Config:
    """
    Load configuration from YAML file and environment variables.

    Priority:
    1. Environment variables (highest)
    2. YAML config file
    3. Default values (lowest)
    """
    # Load .env file if present
    load_dotenv()

    config = Config()

    # Load from YAML if provided
    if config_path and Path(config_path).exists():
        with open(config_path) as f:
            yaml_config = yaml.safe_load(f)

        if yaml_config:
            if 'database' in yaml_config:
                config.database_path = yaml_config['database'].get('path', config.database_path)

            if 'vector_store' in yaml_config:
                vs = yaml_config['vector_store']
                config.vector_store.path = vs.get('path', config.vector_store.path)
                config.vector_store.collection_name = vs.get('collection_name', config.vector_store.collection_name)

            if 'embeddings' in yaml_config:
                emb = yaml_config['embeddings']
                config.embeddings.provider = emb.get('provider', config.embeddings.provider)
                config.embeddings.model = emb.get('model', config.embeddings.model)
                config.embeddings.batch_size = emb.get('batch_size', config.embeddings.batch_size)
                config.embeddings.cache_embeddings = emb.get('cache_embeddings', config.embeddings.cache_embeddings)

            if 'llm' in yaml_config:
                llm = yaml_config['llm']
                config.llm.provider = llm.get('provider', config.llm.provider)
                config.llm.model = llm.get('model', config.llm.model)
                config.llm.max_tokens = llm.get('max_tokens', config.llm.max_tokens)
                config.llm.temperature = llm.get('temperature', config.llm.temperature)

            if 'chunking' in yaml_config:
                ch = yaml_config['chunking']
                config.chunking.target_duration_seconds = ch.get('target_duration_seconds', config.chunking.target_duration_seconds)
                config.chunking.overlap_ratio = ch.get('overlap_ratio', config.chunking.overlap_ratio)
                config.chunking.min_tokens = ch.get('min_tokens', config.chunking.min_tokens)
                config.chunking.max_tokens = ch.get('max_tokens', config.chunking.max_tokens)

            if 'deduplication' in yaml_config:
                dd = yaml_config['deduplication']
                config.deduplication.similarity_threshold = dd.get('similarity_threshold', config.deduplication.similarity_threshold)
                config.deduplication.min_cluster_size = dd.get('min_cluster_size', config.deduplication.min_cluster_size)

    # Load API keys from environment (override YAML)
    config.anthropic_api_key = os.getenv('ANTHROPIC_API_KEY')
    config.openai_api_key = os.getenv('OPENAI_API_KEY') or os.getenv('OPENAI_SECRET_KEY')

    # Also check for alternative env var names
    if not config.database_path or config.database_path == "data/transcripts.db":
        config.database_path = os.getenv('COURSE_BUILDER_DB_PATH', config.database_path)

    if config.vector_store.path == "chroma_data":
        config.vector_store.path = os.getenv('COURSE_BUILDER_CHROMA_PATH', config.vector_store.path)

    return config


# Default config file path
DEFAULT_CONFIG_PATH = "config.yaml"
