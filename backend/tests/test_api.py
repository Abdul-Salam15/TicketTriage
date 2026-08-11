import os
import pytest
from fastapi.testclient import TestClient

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_tickets.db")

import main
from schemas import TriageResult

GOOD_PASSWORD = "Testpass1!"


class FakeProvider:
    async def triage_ticket(self, subject: str, description: str) -> TriageResult:
        return TriageResult(category="Bug", priority="High", reply="We're on it.")


class FailingProvider:
    async def triage_ticket(self, subject: str, description: str) -> TriageResult:
        raise RuntimeError("rate limit exceeded")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(main, "get_llm_provider", lambda: FakeProvider())
    return TestClient(main.app)


def _register(client, email):
    res = client.post("/auth/register", json={"email": email, "password": GOOD_PASSWORD})
    assert res.status_code == 201
    return res.json()["token"]


def test_full_ticket_flow(client):
    token = _register(client, "flow@example.com")
    auth = {"Authorization": f"Bearer {token}"}

    created = client.post("/tickets", json={"subject": "Login broken", "description": "500 on submit"}, headers=auth)
    assert created.status_code == 201
    body = created.json()
    assert body["category"] == "Bug" and body["priority"] == "High"
    assert len(body["ticket_code"]) == 7

    listed = client.get("/tickets", headers=auth)
    assert listed.status_code == 200 and len(listed.json()) == 1

    edited = client.patch(f"/tickets/{body['id']}", json={"reply": "Custom reply"}, headers=auth)
    assert edited.json()["suggested_reply"] == "Custom reply"


def test_empty_input_rejected(client):
    auth = {"Authorization": f"Bearer {_register(client, 'empty@example.com')}"}
    res = client.post("/tickets", json={"subject": "   ", "description": ""}, headers=auth)
    assert res.status_code == 422


def test_llm_failure_returns_502_and_saves_nothing(client, monkeypatch):
    auth = {"Authorization": f"Bearer {_register(client, 'fail@example.com')}"}
    monkeypatch.setattr(main, "get_llm_provider", lambda: FailingProvider())

    res = client.post("/tickets", json={"subject": "s", "description": "d"}, headers=auth)
    assert res.status_code == 502
    assert "rate-limited" in res.json()["detail"]
    assert client.get("/tickets", headers=auth).json() == []


def test_tickets_are_not_visible_across_users(client):
    a = {"Authorization": f"Bearer {_register(client, 'a@example.com')}"}
    b = {"Authorization": f"Bearer {_register(client, 'b@example.com')}"}

    ticket_id = client.post("/tickets", json={"subject": "s", "description": "d"}, headers=a).json()["id"]
    assert client.get(f"/tickets/{ticket_id}", headers=b).status_code == 404
    assert client.get("/tickets", headers=b).json() == []


def test_auth_required(client):
    assert client.get("/tickets").status_code == 401
    assert client.get("/tickets", headers={"Authorization": "Bearer nonsense"}).status_code == 401
