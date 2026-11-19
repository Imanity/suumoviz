from pathlib import Path

import pytest

from suumoviz import codec

FIXTURES = Path(__file__).parent / "fixtures" / "suumo"


@pytest.fixture
def fixture_bytes():
    def load(name: str) -> bytes:
        return codec.read_bytes(FIXTURES / name)  # fixtures are stored obfuscated

    return load


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unit tests must never reach the network."""

    def refuse(*args: object, **kwargs: object) -> None:
        raise RuntimeError("network access is not allowed in tests")

    monkeypatch.setattr("socket.socket.connect", refuse)
    monkeypatch.setattr("socket.create_connection", refuse)
