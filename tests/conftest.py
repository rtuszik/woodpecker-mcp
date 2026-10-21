from collections.abc import AsyncIterator, Iterable

import httpx2
import pytest

from woodpecker_mcp.spec import load_spec


@pytest.fixture(scope="session")
def raw_spec() -> dict:
    return load_spec()


class TrackedStream(httpx2.AsyncByteStream):
    def __init__(self, chunks: Iterable[bytes]):
        self.chunks = chunks
        self.chunks_read = 0
        self.closed = False

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            self.chunks_read += 1
            yield chunk

    async def aclose(self) -> None:
        self.closed = True


@pytest.fixture
def tracked_stream():
    return TrackedStream
