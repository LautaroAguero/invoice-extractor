"""API-free stand-ins for the Anthropic SDK."""

import asyncio
from collections.abc import Iterable
from typing import Any

from anthropic.types import Message


def make_message(
    text: str | None,
    *,
    stop_reason: str = "end_turn",
    input_tokens: int = 5_000,
    output_tokens: int = 2_000,
    cache_read: int | None = None,
    cache_creation: int | None = None,
    model: str = "claude-sonnet-5",
) -> Message:
    content = [{"type": "text", "text": text, "citations": None}] if text is not None else []
    return Message.model_validate(
        {
            "id": "msg_fake",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": content,
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "cache_read_input_tokens": cache_read,
                "cache_creation_input_tokens": cache_creation,
            },
        }
    )


class FakeMessages:
    def __init__(self, responses: Iterable[Message | BaseException], delay: float = 0.0) -> None:
        self._responses = list(responses)
        self._delay = delay
        self.requests: list[dict[str, Any]] = []

    async def create(self, **kwargs: Any) -> Message:
        self.requests.append(kwargs)
        if self._delay:
            await asyncio.sleep(self._delay)
        response = self._responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class FakeSdk:
    """Scripted responses (messages or exceptions), returned in order; records every request."""

    def __init__(self, *responses: Message | BaseException, delay: float = 0.0) -> None:
        self.messages = FakeMessages(responses, delay)
