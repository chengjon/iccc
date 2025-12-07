"""Tests for event summarization."""

import pytest
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from iccc.models.entities import HookEvent
from iccc.observability.event_summarizer import (
    EventSummarizer,
    SummaryCache,
    quick_summarize,
)


@pytest.fixture
def sample_events():
    """Create sample events for testing."""
    return [
        HookEvent(
            id=uuid4(),
            session_id=uuid4(),
            event_type="PostToolUse",
            timestamp=datetime.now(),
            data={
                "tool_name": "Write",
                "file_path": "/src/main.py",
                "status": "success",
                "agent_id": "agent-001",
            },
        ),
        HookEvent(
            id=uuid4(),
            session_id=uuid4(),
            event_type="PostToolUse",
            timestamp=datetime.now(),
            data={
                "tool_name": "Bash",
                "command": "npm test",
                "status": "success",
                "agent_id": "agent-001",
            },
        ),
        HookEvent(
            id=uuid4(),
            session_id=uuid4(),
            event_type="Error",
            timestamp=datetime.now(),
            data={
                "error": "Connection timeout",
                "agent_id": "agent-002",
            },
        ),
    ]


class TestSummaryCache:
    """Tests for SummaryCache."""

    def test_cache_set_and_get(self):
        """Test basic cache operations."""
        cache = SummaryCache()

        cache.set("test_data", "test_summary")
        result = cache.get("test_data")

        assert result == "test_summary"

    def test_cache_miss(self):
        """Test cache miss."""
        cache = SummaryCache()

        result = cache.get("nonexistent")

        assert result is None

    def test_cache_max_size(self):
        """Test cache eviction at max size."""
        cache = SummaryCache(max_size=3)

        cache.set("data1", "summary1")
        cache.set("data2", "summary2")
        cache.set("data3", "summary3")
        cache.set("data4", "summary4")  # Should evict oldest

        # Cache should have 3 items
        assert cache.get("data4") == "summary4"
        # data1 might be evicted (oldest)

    def test_cache_clear(self):
        """Test cache clear."""
        cache = SummaryCache()
        cache.set("data", "summary")

        cache.clear()

        assert cache.get("data") is None


class TestEventSummarizer:
    """Tests for EventSummarizer."""

    def test_init_without_api_key(self):
        """Test initialization without API key."""
        with patch.dict("os.environ", {}, clear=True):
            summarizer = EventSummarizer(api_key=None)

            assert summarizer.client is None

    def test_init_with_api_key(self):
        """Test initialization with API key."""
        summarizer = EventSummarizer(api_key="test-key")

        assert summarizer.client is not None
        assert summarizer.model == "claude-3-5-haiku-latest"

    def test_format_events(self, sample_events):
        """Test event formatting."""
        summarizer = EventSummarizer(api_key="test-key")

        formatted = summarizer._format_events(sample_events)

        assert "PostToolUse" in formatted
        assert "Error" in formatted
        assert "agent-001" in formatted

    def test_summarize_event_data(self):
        """Test event data summarization."""
        summarizer = EventSummarizer(api_key="test-key")

        data = {
            "tool_name": "Write",
            "file_path": "/test.py",
            "status": "success",
        }

        summary = summarizer._summarize_event_data(data)

        assert "tool=Write" in summary
        assert "file=/test.py" in summary
        assert "status=success" in summary

    @pytest.mark.asyncio
    async def test_summarize_events_no_client(self, sample_events):
        """Test summarization without client returns None."""
        summarizer = EventSummarizer(api_key=None, silent_failures=True)

        result = await summarizer.summarize_events(sample_events)

        assert result is None

    @pytest.mark.asyncio
    async def test_summarize_events_empty_list(self):
        """Test summarization with empty list."""
        summarizer = EventSummarizer(api_key="test-key")

        result = await summarizer.summarize_events([])

        assert result is None

    @pytest.mark.asyncio
    async def test_summarize_events_with_cache(self, sample_events):
        """Test that caching works."""
        summarizer = EventSummarizer(api_key="test-key", enable_cache=True)

        # Mock the client
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Test summary")]
        mock_response.usage = MagicMock(input_tokens=10, output_tokens=5)

        summarizer.client = AsyncMock()
        summarizer.client.messages.create = AsyncMock(return_value=mock_response)

        # First call - should hit API
        result1 = await summarizer.summarize_events(sample_events)

        # Second call with same events - should hit cache
        result2 = await summarizer.summarize_events(sample_events)

        assert result1 == "Test summary"
        assert result2 == "Test summary"
        assert summarizer.stats.cache_hits == 1
        assert summarizer.stats.cache_misses == 1

    @pytest.mark.asyncio
    async def test_summarize_single_event(self, sample_events):
        """Test single event summarization."""
        summarizer = EventSummarizer(api_key="test-key")

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Single event summary")]
        mock_response.usage = MagicMock(input_tokens=5, output_tokens=3)

        summarizer.client = AsyncMock()
        summarizer.client.messages.create = AsyncMock(return_value=mock_response)

        result = await summarizer.summarize_event(sample_events[0])

        assert result == "Single event summary"

    @pytest.mark.asyncio
    async def test_summarize_by_agent(self, sample_events):
        """Test summarization grouped by agent."""
        summarizer = EventSummarizer(api_key="test-key")

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Agent summary")]
        mock_response.usage = MagicMock(input_tokens=5, output_tokens=3)

        summarizer.client = AsyncMock()
        summarizer.client.messages.create = AsyncMock(return_value=mock_response)

        result = await summarizer.summarize_by_agent(sample_events)

        assert "agent-001" in result
        assert "agent-002" in result

    @pytest.mark.asyncio
    async def test_summarize_different_styles(self, sample_events):
        """Test different summary styles."""
        summarizer = EventSummarizer(api_key="test-key")

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Styled summary")]
        mock_response.usage = MagicMock(input_tokens=5, output_tokens=3)

        summarizer.client = AsyncMock()
        summarizer.client.messages.create = AsyncMock(return_value=mock_response)

        for style in ["concise", "detailed", "technical", "dashboard"]:
            result = await summarizer.summarize_events(sample_events, style=style)
            assert result is not None

    def test_get_stats(self):
        """Test statistics retrieval."""
        summarizer = EventSummarizer(api_key="test-key")

        stats = summarizer.get_stats()

        assert "total_requests" in stats
        assert "cache_hits" in stats
        assert "model" in stats
        assert stats["model"] == "claude-3-5-haiku-latest"

    def test_clear_cache(self):
        """Test cache clearing."""
        summarizer = EventSummarizer(api_key="test-key", enable_cache=True)
        summarizer.cache.set("test", "data")

        summarizer.clear_cache()

        assert summarizer.cache.get("test") is None

    @pytest.mark.asyncio
    async def test_silent_failure_mode(self, sample_events):
        """Test that errors are silently handled."""
        summarizer = EventSummarizer(api_key="test-key", silent_failures=True)

        summarizer.client = AsyncMock()
        summarizer.client.messages.create = AsyncMock(side_effect=Exception("API Error"))

        result = await summarizer.summarize_events(sample_events)

        assert result is None
        assert summarizer.stats.errors == 1

    @pytest.mark.asyncio
    async def test_error_raised_when_not_silent(self, sample_events):
        """Test that errors are raised when not in silent mode."""
        summarizer = EventSummarizer(api_key="test-key", silent_failures=False)

        summarizer.client = AsyncMock()
        summarizer.client.messages.create = AsyncMock(side_effect=Exception("API Error"))

        with pytest.raises(RuntimeError, match="Summary generation failed"):
            await summarizer.summarize_events(sample_events)


class TestQuickSummarize:
    """Tests for quick_summarize helper."""

    @pytest.mark.asyncio
    async def test_quick_summarize_no_api_key(self, sample_events):
        """Test quick summarize without API key."""
        with patch.dict("os.environ", {}, clear=True):
            result = await quick_summarize(sample_events)

            assert result is None
