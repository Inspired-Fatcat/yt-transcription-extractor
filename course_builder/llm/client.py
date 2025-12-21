"""Claude API client wrapper."""

from typing import Optional, TypeVar, Type
import json

from anthropic import Anthropic
from pydantic import BaseModel

from ..config import LLMConfig


T = TypeVar('T', bound=BaseModel)


class ClaudeClient:
    """Wrapper for Claude API with structured output support."""

    def __init__(self, api_key: str, config: Optional[LLMConfig] = None):
        self.client = Anthropic(api_key=api_key)
        self.config = config or LLMConfig()

    def complete(
        self,
        prompt: str,
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """
        Send a completion request to Claude.

        Args:
            prompt: The user message
            system: Optional system prompt
            max_tokens: Override default max tokens
            temperature: Override default temperature

        Returns:
            The assistant's response text
        """
        messages = [{"role": "user", "content": prompt}]

        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=max_tokens or self.config.max_tokens,
            temperature=temperature if temperature is not None else self.config.temperature,
            system=system or "",
            messages=messages,
        )

        return response.content[0].text

    def complete_json(
        self,
        prompt: str,
        response_model: Type[T],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> T:
        """
        Get a structured JSON response from Claude.

        Args:
            prompt: The user message
            response_model: Pydantic model class for the response
            system: Optional system prompt
            max_tokens: Override default max tokens

        Returns:
            Parsed Pydantic model instance
        """
        # Build system prompt with JSON instruction
        json_system = system or ""
        json_system += "\n\nYou must respond with valid JSON that matches the requested schema. Do not include any other text, only the JSON object."

        # Add schema to prompt
        schema_prompt = f"""{prompt}

Respond with a JSON object matching this schema:
{json.dumps(response_model.model_json_schema(), indent=2)}

Return ONLY the JSON object, no other text."""

        response_text = self.complete(
            prompt=schema_prompt,
            system=json_system,
            max_tokens=max_tokens,
            temperature=0.1,  # Lower temperature for structured output
        )

        # Parse JSON from response
        # Handle potential markdown code blocks
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        data = json.loads(text)
        return response_model.model_validate(data)

    def complete_list(
        self,
        prompt: str,
        item_model: Type[T],
        system: Optional[str] = None,
        max_tokens: Optional[int] = None,
    ) -> list[T]:
        """
        Get a list of structured items from Claude.

        Args:
            prompt: The user message
            item_model: Pydantic model class for each item
            system: Optional system prompt
            max_tokens: Override default max tokens

        Returns:
            List of parsed Pydantic model instances
        """
        # Build system prompt with JSON instruction
        json_system = system or ""
        json_system += "\n\nYou must respond with a valid JSON array. Do not include any other text, only the JSON array."

        schema_prompt = f"""{prompt}

Respond with a JSON array where each item matches this schema:
{json.dumps(item_model.model_json_schema(), indent=2)}

Return ONLY the JSON array, no other text."""

        response_text = self.complete(
            prompt=schema_prompt,
            system=json_system,
            max_tokens=max_tokens,
            temperature=0.1,
        )

        # Parse JSON from response
        text = response_text.strip()
        if text.startswith("```json"):
            text = text[7:]
        if text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

        data = json.loads(text)
        return [item_model.model_validate(item) for item in data]
