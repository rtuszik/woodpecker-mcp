"""Shared upstream handling for the hand-written tools."""

import httpx2


def raise_for_status(response: httpx2.Response) -> None:
    """Fail like the generated tools: status, reason and body, no upstream URL."""
    if response.is_success:
        return
    message = f"HTTP error {response.status_code}: {response.reason_phrase}"
    if response.text:
        message += f" - {response.text}"
    raise httpx2.HTTPStatusError(message, request=response.request, response=response)
