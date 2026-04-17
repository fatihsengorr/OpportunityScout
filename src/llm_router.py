"""
LLM Router — Unified interface for Claude and Gemini API calls.

Routes requests to the appropriate provider based on config:
- Gemini 2.5 Flash: daily scans (cheap, Google Search built-in)
- Claude Sonnet 4: weekly deep analysis + scoring (best reasoning)

Returns Anthropic-compatible response objects so existing engine code
needs minimal changes — just replace `self.client` with `self.llm`.
"""

import os
import json
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("scout.llm_router")

# ─── Anthropic-compatible response objects ────────────────────

@dataclass
class TextBlock:
    """Mimics Anthropic's TextBlock."""
    type: str = "text"
    text: str = ""


@dataclass
class ToolUseBlock:
    """Mimics Anthropic's ToolUse block (for web search loop compat)."""
    type: str = "tool_use"
    id: str = "gemini_search"
    name: str = "web_search"
    input: dict = field(default_factory=dict)


@dataclass
class LLMResponse:
    """Unified response object — works with existing engine code.

    Engines check:
      - response.stop_reason == "tool_use"  (to continue loop)
      - response.content  (list of blocks)
      - block.type == "tool_use" / hasattr(block, 'text')
      - block.id  (for tool_result messages)
    """
    content: list = field(default_factory=list)
    stop_reason: str = "end_turn"


# ─── Provider implementations ──────────────────────────────────

class ClaudeProvider:
    """Thin wrapper around Anthropic SDK — preserves existing behavior.

    Implements prompt caching (cache_control: ephemeral) for system prompts
    over 1024 tokens. Cache hits cost 10% of normal input pricing.
    5-minute TTL, auto-refreshed on each hit.
    """

    # Anthropic prompt caching requires min 1024 tokens (Sonnet/Opus)
    # Our SYSTEM_PROMPT.md is ~2200 tokens — well above threshold
    CACHE_MIN_CHARS = 4096  # ~1024 tokens at 4 chars/token

    def __init__(self, api_key: str):
        from anthropic import Anthropic
        self.client = Anthropic(api_key=api_key)
        logger.info("🟣 Claude provider initialized (prompt caching enabled)")

    def create(self, *, model: str, max_tokens: int,
               messages: list, system: str = None,
               tools: list = None) -> LLMResponse:
        """Direct passthrough to Anthropic API with prompt caching on system prompt."""
        kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": messages,
        }

        if system:
            # Apply cache_control to system prompt if large enough
            # System becomes a list of content blocks instead of a plain string
            if len(system) >= self.CACHE_MIN_CHARS:
                kwargs["system"] = [
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"}
                    }
                ]
            else:
                kwargs["system"] = system

        if tools:
            kwargs["tools"] = tools

        response = self.client.messages.create(**kwargs)

        # Return native Anthropic response — engines already know how to parse it
        return response


class GeminiProvider:
    """Gemini adapter that returns Anthropic-compatible response objects."""

    def __init__(self, api_key: str):
        from google import genai
        self.genai = genai
        self.client = genai.Client(api_key=api_key)
        logger.info("🔵 Gemini provider initialized")

    def create(self, *, model: str, max_tokens: int,
               messages: list, system: str = None,
               tools: list = None) -> LLMResponse:
        """Convert Anthropic-style call to Gemini, return compatible response."""
        from google.genai.types import (
            GenerateContentConfig, GoogleSearch, Tool, Content, Part
        )

        # --- Build Gemini contents from Anthropic messages ---
        contents = self._convert_messages(messages)

        # --- Build config ---
        config_kwargs = {
            "max_output_tokens": max_tokens,
        }

        if system:
            config_kwargs["system_instruction"] = system

        # --- Handle tools (only web_search in our codebase) ---
        has_search = False
        if tools:
            for t in tools:
                if isinstance(t, dict) and "web_search" in t.get("type", ""):
                    has_search = True
                    break

        if has_search:
            config_kwargs["tools"] = [Tool(google_search=GoogleSearch())]

        config = GenerateContentConfig(**config_kwargs)

        # --- Call Gemini with retry for 503/429 ---
        import time
        last_error = None
        for attempt in range(3):
            try:
                response = self.client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                last_error = None
                break
            except Exception as e:
                last_error = e
                err_str = str(e)
                if "503" in err_str or "429" in err_str or "UNAVAILABLE" in err_str:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"🔵 Gemini retry {attempt+1}/3 after {wait}s: {err_str[:100]}")
                    time.sleep(wait)
                else:
                    logger.error(f"🔵 Gemini API error: {e}")
                    return LLMResponse(
                        content=[TextBlock(text=f"Error: {e}")],
                        stop_reason="error"
                    )

        if last_error:
            logger.error(f"🔵 Gemini failed after 3 retries: {last_error}")
            return LLMResponse(
                content=[TextBlock(text=f"Error: {last_error}")],
                stop_reason="error"
            )

        # --- Convert Gemini response to Anthropic-compatible format ---
        return self._convert_response(response, has_search)

    def _convert_messages(self, messages: list) -> list:
        """Convert Anthropic messages format to Gemini contents."""
        from google.genai.types import Content, Part

        contents = []
        for msg in messages:
            role = "user" if msg["role"] == "user" else "model"
            content = msg.get("content", "")

            if isinstance(content, str):
                contents.append(Content(
                    role=role,
                    parts=[Part(text=content)]
                ))
            elif isinstance(content, list):
                # Handle Anthropic's content block lists
                parts = []
                for block in content:
                    if isinstance(block, dict):
                        # tool_result blocks from the loop
                        if block.get("type") == "tool_result":
                            parts.append(Part(text=block.get("content", "Search completed.")))
                        elif block.get("type") == "text":
                            parts.append(Part(text=block.get("text", "")))
                    elif hasattr(block, 'text'):
                        # Anthropic TextBlock objects
                        parts.append(Part(text=block.text))
                    elif hasattr(block, 'type') and block.type == "tool_use":
                        # Anthropic ToolUse block — skip in Gemini context
                        # (Gemini handles search internally)
                        parts.append(Part(text=f"[Web search: {getattr(block, 'name', 'search')}]"))
                    elif hasattr(block, 'type') and block.type == "web_search_tool_result":
                        # Anthropic web search result block — summarize for Gemini
                        parts.append(Part(text="[Search results received]"))

                if parts:
                    contents.append(Content(role=role, parts=parts))

        return contents

    def _convert_response(self, response, has_search: bool) -> LLMResponse:
        """Convert Gemini response to Anthropic-compatible LLMResponse."""
        # Check if Gemini wants to do more searching
        # Gemini handles search internally — the response text already
        # includes grounded information. No multi-turn search loop needed.

        text_parts = []
        try:
            if response.candidates and response.candidates[0].content:
                for part in response.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        text_parts.append(part.text)
        except Exception as e:
            logger.warning(f"🔵 Gemini response parse warning: {e}")

        full_text = "\n".join(text_parts) if text_parts else ""

        # Gemini does search grounding in a single call — no tool_use loop needed
        # Always return stop_reason="end_turn" so engines don't loop
        return LLMResponse(
            content=[TextBlock(text=full_text)],
            stop_reason="end_turn"
        )


# ─── Router ────────────────────────────────────────────────────

# Model name mapping
GEMINI_MODELS = {
    "gemini-2.5-flash": "gemini-2.5-flash",
    "gemini-2.5-pro": "gemini-2.5-pro",
}

CLAUDE_MODELS = {
    "claude-sonnet-4-20250514": "claude-sonnet-4-20250514",
    "claude-opus-4-20250514": "claude-opus-4-20250514",
    "claude-haiku-3-5-20250415": "claude-haiku-3-5-20250415",
}


class LLMRouter:
    """Routes API calls to the appropriate provider based on model name.

    Usage (drop-in replacement for Anthropic client):
        # Before: self.client = Anthropic(api_key=key)
        # After:  self.llm = LLMRouter(config)

        # Before: response = self.client.messages.create(model=..., ...)
        # After:  response = self.llm.create(model=..., ...)
    """

    def __init__(self, config: dict):
        self._providers = {}
        self._config = config

        # Initialize Claude provider (always needed for scoring/weekly)
        claude_key = (config.get('claude', {}).get('api_key')
                      or os.environ.get('ANTHROPIC_API_KEY'))
        if claude_key:
            self._providers['claude'] = ClaudeProvider(claude_key)

        # Initialize Gemini provider (for daily scans)
        gemini_key = (config.get('gemini', {}).get('api_key')
                      or os.environ.get('GEMINI_API_KEY'))
        if gemini_key:
            self._providers['gemini'] = GeminiProvider(gemini_key)

        providers = list(self._providers.keys())
        logger.info(f"🔀 LLM Router initialized — providers: {providers}")

    @property
    def messages(self):
        """Compatibility shim: allows `router.messages.create(...)` syntax."""
        return self

    def create(self, *, model: str, max_tokens: int,
               messages: list, system: str = None,
               tools: list = None):
        """Route to the appropriate provider based on model name."""
        provider = self._get_provider(model)
        return provider.create(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            system=system,
            tools=tools,
        )

    def _get_provider(self, model: str):
        """Determine which provider to use based on model name."""
        if model.startswith("gemini"):
            if 'gemini' in self._providers:
                return self._providers['gemini']
            else:
                logger.warning(f"🔵 Gemini requested but not configured, falling back to Claude")
                return self._providers['claude']
        else:
            # Default to Claude for all claude-* models
            if 'claude' in self._providers:
                return self._providers['claude']
            else:
                raise RuntimeError("No Claude provider configured")

    # ─── Model name helpers ─────────────────────────────────

    def get_model(self, mode: str = "daily") -> str:
        """Get the configured model name for a given mode.

        Modes:
          - daily: Gemini Flash (cheap) or Claude Sonnet (fallback)
          - weekly: Claude Sonnet (was Opus, now Sonnet for cost saving)
          - scoring: Claude Sonnet (reliable structured output)
        """
        models = self._config.get('models', {})

        if mode == "daily":
            return models.get('daily', 'gemini-2.5-flash')
        elif mode == "weekly":
            return models.get('weekly', 'claude-sonnet-4-20250514')
        elif mode == "scoring":
            return models.get('scoring', 'claude-sonnet-4-20250514')
        elif mode == "deep":
            # Deep dive on demand — use weekly model
            return models.get('weekly', 'claude-sonnet-4-20250514')
        else:
            return models.get('daily', 'gemini-2.5-flash')
