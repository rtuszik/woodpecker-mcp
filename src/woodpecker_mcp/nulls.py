"""Turn null list bodies into empty lists.

Go encodes a nil slice as null, so list endpoints with no items send null, not [].
"""

import httpx2


class NullListTransport(httpx2.AsyncBaseTransport):
    def __init__(self, inner: httpx2.AsyncBaseTransport) -> None:
        self._inner = inner

    async def handle_async_request(self, request: httpx2.Request) -> httpx2.Response:
        response = await self._inner.handle_async_request(request)
        content_type = response.headers.get("content-type", "")
        if not response.is_success or not content_type.startswith("application/json"):
            return response
        if (await response.aread()).strip() != b"null":
            return response
        return httpx2.Response(
            response.status_code,
            headers={"content-type": "application/json"},
            content=b"[]",
            request=request,
        )

    async def aclose(self) -> None:
        await self._inner.aclose()
