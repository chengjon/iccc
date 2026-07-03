"""Unit tests for Claude API client."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from iccc.agents.client import ClaudeClient
from iccc.errors.exceptions import ModelOverloadedError, RateLimitError
from iccc.models.entities import Message, ModelTier


class TestClaudeClientInit:
    """Tests for ClaudeClient initialization."""

    def test_init_with_api_key(self):
        """Test initialization with explicit API key."""
        with patch("iccc.agents.client.AsyncAnthropic") as mock_async:
            with patch("iccc.agents.client.Anthropic") as mock_sync:
                with patch("iccc.agents.client.get_rate_limiter") as mock_limiter:
                    client = ClaudeClient(api_key="test-key")

                    assert client.api_key == "test-key"
                    mock_async.assert_called_once_with(api_key="test-key")
                    mock_sync.assert_called_once_with(api_key="test-key")
                    mock_limiter.assert_called_once()

    def test_init_with_env_var(self):
        """Test initialization with environment variable."""
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "env-key"}):
            with patch("iccc.agents.client.AsyncAnthropic"):
                with patch("iccc.agents.client.Anthropic"):
                    with patch("iccc.agents.client.get_rate_limiter"):
                        client = ClaudeClient()
                        assert client.api_key == "env-key"

    def test_init_without_api_key_raises(self):
        """Test initialization without API key raises ValueError."""
        # Mock get_config to return config with empty API key
        mock_config = MagicMock()
        mock_config.anthropic.api_key = ""
        
        with patch("iccc.agents.client.get_config", return_value=mock_config):
            with pytest.raises(ValueError, match="ANTHROPIC_API_KEY not provided"):
                ClaudeClient(api_key=None)

    def test_init_with_redis_client(self):
        """Test initialization with Redis client for distributed rate limiting."""
        mock_redis = MagicMock()
        with patch("iccc.agents.client.AsyncAnthropic"):
            with patch("iccc.agents.client.Anthropic"):
                with patch("iccc.agents.client.get_rate_limiter") as mock_limiter:
                    ClaudeClient(api_key="test-key", redis_client=mock_redis)
                    mock_limiter.assert_called_once_with(mock_redis)


class TestClaudeClientSendMessage:
    """Tests for ClaudeClient.send_message()."""

    @pytest.fixture
    def mock_client(self):
        """Create a mocked ClaudeClient."""
        with patch("iccc.agents.client.AsyncAnthropic") as mock_async:
            with patch("iccc.agents.client.Anthropic"):
                with patch("iccc.agents.client.get_rate_limiter") as mock_limiter:
                    mock_limiter.return_value = AsyncMock()
                    client = ClaudeClient(api_key="test-key")
                    client.client = mock_async.return_value
                    yield client

    @pytest.mark.asyncio
    async def test_send_message_success(self, mock_client):
        """Test successful message sending."""
        # Setup mock response
        mock_response = MagicMock()
        mock_content_block = MagicMock()
        mock_content_block.type = "text"
        mock_content_block.text = "Hello from Claude"
        mock_response.content = [mock_content_block]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hello")]
        result = await mock_client.send_message(messages)

        assert result["content"] == "Hello from Claude"
        assert result["usage"]["input_tokens"] == 10
        assert result["usage"]["output_tokens"] == 5
        assert result["stop_reason"] == "end_turn"
        assert result["model"] == "claude-sonnet-4-20250514"

    @pytest.mark.asyncio
    async def test_send_message_with_system_prompt(self, mock_client):
        """Test message sending with system prompt."""
        mock_response = MagicMock()
        mock_content_block = MagicMock()
        mock_content_block.type = "text"
        mock_content_block.text = "Response"
        mock_response.content = [mock_content_block]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hello")]
        await mock_client.send_message(messages, system="You are helpful.")

        # Verify system prompt was passed
        call_kwargs = mock_client.client.messages.create.call_args[1]
        assert call_kwargs["system"] == "You are helpful."

    @pytest.mark.asyncio
    async def test_send_message_with_custom_model(self, mock_client):
        """Test message sending with custom model tier."""
        mock_response = MagicMock()
        mock_content_block = MagicMock()
        mock_content_block.type = "text"
        mock_content_block.text = "Response"
        mock_response.content = [mock_content_block]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-3-5-haiku-20241022"

        mock_client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hello")]
        await mock_client.send_message(messages, model=ModelTier.HAIKU)

        # Verify correct model was used
        call_kwargs = mock_client.client.messages.create.call_args[1]
        assert "haiku" in call_kwargs["model"].lower()

    @pytest.mark.asyncio
    async def test_send_message_with_custom_max_tokens(self, mock_client):
        """Test message sending with custom max_tokens."""
        mock_response = MagicMock()
        mock_content_block = MagicMock()
        mock_content_block.type = "text"
        mock_content_block.text = "Response"
        mock_response.content = [mock_content_block]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hello")]
        await mock_client.send_message(messages, max_tokens=500)

        call_kwargs = mock_client.client.messages.create.call_args[1]
        assert call_kwargs["max_tokens"] == 500

    @pytest.mark.asyncio
    async def test_send_message_with_temperature(self, mock_client):
        """Test message sending with custom temperature."""
        mock_response = MagicMock()
        mock_content_block = MagicMock()
        mock_content_block.type = "text"
        mock_content_block.text = "Response"
        mock_response.content = [mock_content_block]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hello")]
        await mock_client.send_message(messages, temperature=0.5)

        call_kwargs = mock_client.client.messages.create.call_args[1]
        assert call_kwargs["temperature"] == 0.5

    @pytest.mark.asyncio
    async def test_send_message_rate_limit_error(self, mock_client):
        """Test rate limit error handling."""
        mock_client.client.messages.create = AsyncMock(
            side_effect=Exception("rate limit exceeded")
        )

        messages = [Message(role="user", content="Hello")]

        with pytest.raises(RateLimitError):
            await mock_client.send_message(messages)

    @pytest.mark.asyncio
    async def test_send_message_model_overloaded_error(self, mock_client):
        """Test model overloaded error handling."""
        mock_client.client.messages.create = AsyncMock(
            side_effect=Exception("model overloaded")
        )

        messages = [Message(role="user", content="Hello")]

        with pytest.raises(ModelOverloadedError):
            await mock_client.send_message(messages)

    @pytest.mark.asyncio
    async def test_send_message_unknown_error_propagates(self, mock_client):
        """Test unknown errors are propagated."""
        mock_client.client.messages.create = AsyncMock(
            side_effect=Exception("unknown error")
        )

        messages = [Message(role="user", content="Hello")]

        with pytest.raises(Exception, match="unknown error"):
            await mock_client.send_message(messages)

    @pytest.mark.asyncio
    async def test_send_message_empty_response(self, mock_client):
        """Test handling of empty response content."""
        mock_response = MagicMock()
        mock_response.content = []
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 0
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hello")]
        result = await mock_client.send_message(messages)

        assert result["content"] == ""

    @pytest.mark.asyncio
    async def test_send_message_acquires_rate_limit(self, mock_client):
        """Test that rate limiter is called before API request."""
        mock_response = MagicMock()
        mock_content_block = MagicMock()
        mock_content_block.type = "text"
        mock_content_block.text = "Response"
        mock_response.content = [mock_content_block]
        mock_response.usage.input_tokens = 10
        mock_response.usage.output_tokens = 5
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-sonnet-4-20250514"

        mock_client.client.messages.create = AsyncMock(return_value=mock_response)

        messages = [Message(role="user", content="Hello")]
        await mock_client.send_message(messages)

        mock_client.rate_limiter.acquire.assert_called_once()


class TestClaudeClientStreamMessage:
    """Tests for ClaudeClient.stream_message()."""

    @pytest.fixture
    def mock_client(self):
        """Create a mocked ClaudeClient."""
        with patch("iccc.agents.client.AsyncAnthropic") as mock_async:
            with patch("iccc.agents.client.Anthropic"):
                with patch("iccc.agents.client.get_rate_limiter") as mock_limiter:
                    mock_limiter.return_value = AsyncMock()
                    client = ClaudeClient(api_key="test-key")
                    client.client = mock_async.return_value
                    yield client

    @pytest.mark.asyncio
    async def test_stream_message_success(self, mock_client):
        """Test successful message streaming."""
        # Setup mock stream
        async def mock_text_stream():
            for chunk in ["Hello", " ", "World"]:
                yield chunk

        mock_stream = MagicMock()
        mock_stream.text_stream = mock_text_stream()
        mock_stream.__aenter__ = AsyncMock(return_value=mock_stream)
        mock_stream.__aexit__ = AsyncMock(return_value=None)

        mock_client.client.messages.stream = MagicMock(return_value=mock_stream)

        messages = [Message(role="user", content="Hello")]
        chunks = []
        async for chunk in mock_client.stream_message(messages):
            chunks.append(chunk)

        assert chunks == ["Hello", " ", "World"]

    @pytest.mark.asyncio
    async def test_stream_message_rate_limit_error(self, mock_client):
        """Test rate limit error during streaming."""
        mock_stream = MagicMock()
        mock_stream.__aenter__ = AsyncMock(side_effect=Exception("rate limit exceeded"))

        mock_client.client.messages.stream = MagicMock(return_value=mock_stream)

        messages = [Message(role="user", content="Hello")]

        with pytest.raises(RateLimitError):
            async for _ in mock_client.stream_message(messages):
                pass

    @pytest.mark.asyncio
    async def test_stream_message_model_overloaded_error(self, mock_client):
        """Test model overloaded error during streaming."""
        mock_stream = MagicMock()
        mock_stream.__aenter__ = AsyncMock(side_effect=Exception("model overloaded"))

        mock_client.client.messages.stream = MagicMock(return_value=mock_stream)

        messages = [Message(role="user", content="Hello")]

        with pytest.raises(ModelOverloadedError):
            async for _ in mock_client.stream_message(messages):
                pass


class TestClaudeClientTokenCounting:
    """Tests for ClaudeClient.count_tokens()."""

    def test_count_tokens_simple(self):
        """Test simple token counting."""
        with patch("iccc.agents.client.AsyncAnthropic"):
            with patch("iccc.agents.client.Anthropic"):
                with patch("iccc.agents.client.get_rate_limiter"):
                    client = ClaudeClient(api_key="test-key")

                    # "Hello World" = 11 chars, ~3 tokens (11 // 4)
                    count = client.count_tokens("Hello World")
                    assert count == 2  # 11 // 4 = 2

    def test_count_tokens_empty_string(self):
        """Test token counting for empty string."""
        with patch("iccc.agents.client.AsyncAnthropic"):
            with patch("iccc.agents.client.Anthropic"):
                with patch("iccc.agents.client.get_rate_limiter"):
                    client = ClaudeClient(api_key="test-key")
                    count = client.count_tokens("")
                    assert count == 0

    def test_count_tokens_long_text(self):
        """Test token counting for long text."""
        with patch("iccc.agents.client.AsyncAnthropic"):
            with patch("iccc.agents.client.Anthropic"):
                with patch("iccc.agents.client.get_rate_limiter"):
                    client = ClaudeClient(api_key="test-key")
                    # 400 chars should be ~100 tokens
                    count = client.count_tokens("x" * 400)
                    assert count == 100


class TestClaudeClientClose:
    """Tests for ClaudeClient.close()."""

    @pytest.mark.asyncio
    async def test_close_client(self):
        """Test closing the client."""
        with patch("iccc.agents.client.AsyncAnthropic") as mock_async:
            with patch("iccc.agents.client.Anthropic"):
                with patch("iccc.agents.client.get_rate_limiter"):
                    client = ClaudeClient(api_key="test-key")
                    client.client = AsyncMock()

                    await client.close()

                    client.client.close.assert_called_once()
