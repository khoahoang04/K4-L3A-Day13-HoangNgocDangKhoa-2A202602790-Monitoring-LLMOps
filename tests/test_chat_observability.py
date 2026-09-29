from __future__ import annotations

import json
import asyncio
from pathlib import Path

import httpx

from app import logging_config
from app.main import app


def test_chat_response_log_exposes_quality_for_dashboard(
    monkeypatch, tmp_path: Path
) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request() -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-01",
                    "session_id": "session-01",
                    "feature": "qa",
                    "message": "Explain observability",
                },
            )

    response = asyncio.run(send_request())

    assert response.status_code == 200
    events = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    response_event = next(event for event in events if event["event"] == "response_sent")
    assert response_event["quality_score"] == response.json()["quality_score"]
    assert response_event["ttft_ms"] == response.json()["ttft_ms"]
    assert response_event["tool_name"] == "retrieval"
    assert response_event["tool_success"] is True


def test_chat_correlation_id_and_enrichment(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "logs.jsonl"
    monkeypatch.setattr(logging_config, "LOG_PATH", log_path)

    async def send_request(headers: dict[str, str] | None = None) -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as client:
            return await client.post(
                "/chat",
                json={
                    "user_id": "student-02",
                    "session_id": "session-02",
                    "feature": "summary",
                    "message": "My card is 4111 2222 3333 4444",
                },
                headers=headers,
            )

    # Test with custom x-request-id
    res1 = asyncio.run(send_request(headers={"x-request-id": "req-custom01"}))
    assert res1.status_code == 200
    assert res1.headers.get("x-request-id") == "req-custom01"
    assert "x-response-time-ms" in res1.headers
    assert res1.json()["correlation_id"] == "req-custom01"

    # Test without custom header -> should auto generate req-<8-hex>
    res2 = asyncio.run(send_request())
    assert res2.status_code == 200
    cid2 = res2.headers.get("x-request-id")
    assert cid2 and cid2.startswith("req-")
    assert len(cid2) == 12  # 'req-' + 8 hex chars

    lines = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]
    for entry in lines:
        if entry.get("service") == "api":
            assert "correlation_id" in entry
            assert entry["correlation_id"] != "MISSING"
            assert "user_id_hash" in entry
            assert "session_id" in entry
            assert "feature" in entry
            assert "model" in entry
            # Ensure PII was scrubbed
            raw = json.dumps(entry)
            assert "4111 2222 3333 4444" not in raw
            if entry.get("event") == "request_received":
                assert "REDACTED_CREDIT_CARD" in raw


