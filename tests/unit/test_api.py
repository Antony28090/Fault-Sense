from fastapi.testclient import TestClient

from faultsense.api import create_app
from faultsense.diagnosis.schema import DiagnosisResponse, Meta
from faultsense.diagnosis.service import UnknownMachine


class FakeService:
    def __init__(self):
        self.calls = []

    def diagnose(self, query, machine_id=None, progress=None):
        self.calls.append((query, machine_id))
        if progress:
            progress("search", {"models": []})
            progress("found", {"codes": ["OHF"], "pages": 3, "top": None})
        if machine_id == "NOPE":
            raise UnknownMachine(machine_id)
        return DiagnosisResponse(
            status="escalate", query=query, machine_id=machine_id, language="en", matched_fault_codes=[],
            probable_causes=[], corrective_actions=[], safety_warnings=[], escalation=None, sources=[],
            meta=Meta(retrieval_top_score=0.1),
        )

    def health(self):
        return {"manuals": ["atv600"], "machines": ["DEMO-PUMP-01"]}


def make_client():
    service = FakeService()
    return TestClient(create_app(lambda: service)), service


def test_diagnose_returns_the_service_response():
    client, service = make_client()
    response = client.post("/diagnose", json={"query": "  OHF on pump  ", "machine_id": "DEMO-PUMP-01"})
    assert response.status_code == 200 and response.json()["status"] == "escalate"
    assert service.calls == [("OHF on pump", "DEMO-PUMP-01")]


def test_blank_and_oversized_queries_are_422():
    client, service = make_client()
    assert client.post("/diagnose", json={"query": "   "}).status_code == 422
    assert client.post("/diagnose", json={"query": "x" * 2001}).status_code == 422
    assert client.post("/diagnose", json={}).status_code == 422
    assert service.calls == []


def test_unknown_machine_is_404():
    client, _ = make_client()
    response = client.post("/diagnose", json={"query": "OHF", "machine_id": "NOPE"})
    assert response.status_code == 404 and "NOPE" in response.json()["detail"]


def test_health():
    client, _ = make_client()
    assert client.get("/health").json() == {"status": "ok", "manuals": ["atv600"], "machines": ["DEMO-PUMP-01"]}


def test_control_characters_are_422_but_newlines_and_tabs_are_kept():
    client, service = make_client()
    assert client.post("/diagnose", json={"query": "OHF\x00 on pump"}).status_code == 422
    assert client.post("/diagnose", json={"query": "OHF\x1b[31m"}).status_code == 422
    assert client.post("/diagnose", json={"query": "pump trips\r\n\twhen hot"}).status_code == 200
    assert service.calls == [("pump trips\r\n\twhen hot", None)]


def test_health_is_503_when_the_database_is_unreachable():
    service = FakeService()
    service.health = lambda: {"manuals": ["atv600"], "machines": [], "database": "unreachable: OperationalError"}
    response = TestClient(create_app(lambda: service)).get("/health")
    assert response.status_code == 503 and response.json()["status"] == "degraded"
    assert response.json()["database"] == "unreachable: OperationalError"


def test_health_is_503_when_the_service_cannot_start():
    def broken_factory():
        raise RuntimeError("connection refused")

    response = TestClient(create_app(broken_factory)).get("/health")
    assert response.status_code == 503 and response.json() == {"status": "unavailable", "error": "RuntimeError"}


def make_catalog(tmp_path):
    from faultsense.api import Catalog

    pdf = tmp_path / "atv600.pdf"
    pdf.write_bytes(b"%PDF-1.4 test")
    return Catalog(
        machines=[{"id": "DEMO-PUMP-01", "manual": "atv600", "family": "ATV600", "description": "Example pump"}],
        manual_files={"atv600": pdf, "atv12": tmp_path / "missing.pdf"},
        engine={"diagnosis": "ollama qwen3.5:4b", "rewrite": "anthropic claude-sonnet-5-5"},
    )


def test_the_operator_page_is_served_at_the_root():
    client, _ = make_client()
    page = client.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert "FaultSense" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200


def test_info_answers_without_starting_the_service(tmp_path):
    started = []

    def factory():
        started.append(True)
        return FakeService()

    client = TestClient(create_app(factory, make_catalog(tmp_path)))
    info = client.get("/info").json()
    assert info["machines"][0] == {"id": "DEMO-PUMP-01", "manual": "atv600", "family": "ATV600",
                                   "description": "Example pump"}
    assert info["engine"]["diagnosis"] == "ollama qwen3.5:4b"
    assert started == []


def test_manual_pdfs_are_served_for_citation_links(tmp_path):
    client = TestClient(create_app(FakeService, make_catalog(tmp_path)))
    pdf = client.get("/manuals/atv600.pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert client.get("/manuals/atv12.pdf").status_code == 404  # known manual, file not downloaded
    assert client.get("/manuals/..%2F.env.pdf").status_code == 404  # only catalogued manuals


def test_page_files_are_revalidated_so_updates_show_up():
    client, _ = make_client()
    for path in ("/", "/static/app.js", "/static/app.css"):
        assert client.get(path).headers.get("cache-control") == "no-cache", path


def stream_events(client, body):
    import json

    with client.stream("POST", "/diagnose/stream", json=body) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        return [json.loads(line) for line in response.iter_lines() if line]


def test_streamed_diagnosis_sends_stages_then_the_answer():
    client, service = make_client()
    events = stream_events(client, {"query": "OHF on pump", "machine_id": "DEMO-PUMP-01"})
    assert [e["event"] for e in events] == ["stage", "stage", "result"]
    assert [e["stage"] for e in events[:2]] == ["search", "found"] and events[1]["codes"] == ["OHF"]
    assert events[2]["response"]["status"] == "escalate"
    assert service.calls == [("OHF on pump", "DEMO-PUMP-01")]


def test_streamed_diagnosis_reports_an_unknown_machine():
    client, _ = make_client()
    events = stream_events(client, {"query": "OHF", "machine_id": "NOPE"})
    assert events[-1]["event"] == "error" and events[-1]["status"] == 404 and "NOPE" in events[-1]["detail"]


def test_streamed_diagnosis_still_validates_the_question():
    client, _ = make_client()
    assert client.post("/diagnose/stream", json={"query": "  "}).status_code == 422


def test_passages_endpoint_returns_the_manual_text():
    service = FakeService()
    service.passage = lambda chunk_id: {"chunk_id": chunk_id, "text": "Fault code OHF"} if chunk_id == "atv600:f:OHF" else None
    client = TestClient(create_app(lambda: service))
    assert client.get("/passages/atv600:f:OHF").json()["text"] == "Fault code OHF"
    assert client.get("/passages/atv600:f:NOPE").status_code == 404
