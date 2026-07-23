import pytest

from woodpecker_mcp.spec import load_spec


@pytest.fixture(scope="session")
def raw_spec() -> dict:
    return load_spec()
