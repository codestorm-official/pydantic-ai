from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.config import get_settings
from app.main import app

client = TestClient(app)


def setup_function() -> None:
    get_settings.cache_clear()


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_web_ui() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "Pydantic AI Agent" in response.text


def test_config_without_key(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.get("/api/config")
    assert response.status_code == 200
    assert response.json() == {"provider": "openai", "model": "gpt-4o-mini", "configured": False}


def test_chat_explains_missing_key(monkeypatch: MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    response = client.post("/api/chat", json={"message": "Hello"})
    assert response.status_code == 500
    assert response.json() == {
        "detail": "Missing OPENAI_API_KEY for provider 'openai'."
    }


def test_chat_rejects_empty_message() -> None:
    response = client.post("/api/chat", json={"message": ""})
    assert response.status_code == 422
