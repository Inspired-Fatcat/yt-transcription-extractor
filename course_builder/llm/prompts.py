"""Prompt templates for LLM operations."""

# System prompts
TOPIC_EXTRACTION_SYSTEM = """You are an expert at analyzing educational content about software development, AI, and coding with AI assistants like Claude Code.

Your task is to extract topics, concepts, and techniques from transcript chunks. Focus on:
- Technical concepts and terminology
- Practical techniques and patterns
- Tools and their usage
- Code examples and demonstrations
- Tips and best practices

Be specific and precise. Prefer concrete terms over vague descriptions."""


DEDUPLICATION_SYSTEM = """You are an expert at comparing educational content to identify duplicates and overlaps.

Your task is to analyze pairs of transcript chunks and determine:
- Whether they cover the same or similar content
- What concepts they share
- What is unique to each
- How they could be merged if duplicates

Be thorough but concise in your analysis."""


CURRICULUM_SYSTEM = """You are an expert curriculum designer for technical education.

Your task is to organize topics into a coherent learning path. Consider:
- Prerequisites and dependencies between topics
- Progressive complexity (beginner → advanced)
- Logical groupings of related concepts
- Practical application and exercises

Design curricula that are engaging and lead to real skill development."""


LESSON_GENERATION_SYSTEM = """You are an expert technical writer creating educational content.

Your task is to synthesize transcript chunks into well-structured lessons. Guidelines:
- Clear, concise explanations
- Practical examples and code snippets
- Step-by-step instructions where appropriate
- Engaging but professional tone

Reference the original transcripts but improve clarity and organization."""


# User prompt templates
def topic_extraction_prompt(chunk_text: str, video_title: str, channel: str) -> str:
    """Generate prompt for extracting topics from a chunk."""
    return f"""Analyze this transcript chunk from the video "{video_title}" by {channel}.

Extract all relevant topics, concepts, and techniques mentioned. For each topic:
1. Give it a clear, specific name
2. Describe what it covers
3. Categorize it (concept, technique, tool, example, or tip)
4. Rate its relevance to the chunk (0.0-1.0)
5. List 3-5 keywords

Also provide:
- The main theme of this chunk
- A 2-3 sentence summary

TRANSCRIPT:
{chunk_text}"""


def batch_topic_extraction_prompt(chunks: list[dict]) -> str:
    """Generate prompt for extracting topics from multiple chunks."""
    chunk_texts = []
    for i, chunk in enumerate(chunks):
        chunk_texts.append(f"[CHUNK {i+1}] (Video: {chunk['video_title']}, Time: {chunk['timestamp']})\n{chunk['text']}")

    return f"""Analyze these transcript chunks and extract topics from EACH chunk separately.

For each chunk, identify:
- Topics/concepts mentioned
- Techniques or patterns described
- Tools referenced
- Examples shown
- Tips or best practices

CHUNKS:
{chr(10).join(chunk_texts)}

Return the topics for each chunk."""


def duplicate_analysis_prompt(chunk1: dict, chunk2: dict) -> str:
    """Generate prompt for analyzing potential duplicates."""
    return f"""Compare these two transcript chunks and analyze their similarity.

CHUNK 1 (Video: {chunk1['video_title']}, Time: {chunk1['timestamp']}):
{chunk1['text']}

CHUNK 2 (Video: {chunk2['video_title']}, Time: {chunk2['timestamp']}):
{chunk2['text']}

Determine:
1. Are these covering the same content? (is_duplicate: true/false)
2. Type of similarity: exact, paraphrase, related, or different
3. What concepts do they share?
4. What is unique to each chunk?
5. If they are duplicates, provide a merged summary that captures all information from both."""


def curriculum_proposal_prompt(topics: list[dict], context: str = "") -> str:
    """Generate prompt for proposing a curriculum."""
    topic_list = "\n".join([f"- {t['name']}: {t['description']}" for t in topics])

    return f"""Based on these extracted topics from educational videos about Claude Code and agentic coding, propose a curriculum structure.

CONTEXT:
{context if context else "Creating a comprehensive course on using Claude Code for software development."}

TOPICS TO ORGANIZE:
{topic_list}

Design a curriculum with:
1. Clear course title and description
2. Target audience
3. Prerequisites
4. 4-8 modules that group related topics logically
5. Learning objectives for each module
6. Suggested sequence (beginner concepts first)

The curriculum should lead to practical skill development in using Claude Code effectively."""


def lesson_generation_prompt(
    lesson_title: str,
    module_context: str,
    source_chunks: list[dict],
    learning_objectives: list[str]
) -> str:
    """Generate prompt for creating lesson content."""
    chunk_texts = []
    for i, chunk in enumerate(source_chunks):
        chunk_texts.append(f"[SOURCE {i+1}] (Video: {chunk['video_title']}, Time: {chunk['timestamp']})\n{chunk['text']}")

    objectives = "\n".join([f"- {obj}" for obj in learning_objectives])

    return f"""Create a lesson titled "{lesson_title}" for the module "{module_context}".

LEARNING OBJECTIVES:
{objectives}

SOURCE MATERIAL:
{chr(10).join(chunk_texts)}

Write a complete lesson that:
1. Introduces the topic clearly
2. Explains key concepts with examples
3. Provides practical guidance
4. Includes code snippets where appropriate
5. Ends with key takeaways
6. Suggests exercises for practice

Format the body in markdown. Be comprehensive but concise."""
