"""HTTP API and operator page: GET /, POST /diagnose, GET /info, GET /health, GET /manuals/{id}.pdf."""
from __future__ import annotations

import json
import queue
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from faultsense.diagnosis.schema import DiagnosisResponse
from faultsense.diagnosis.service import UnknownMachine

# NUL breaks the Postgres text search; control characters other than tab, CR and LF are never part of a report.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
WEB_DIR = Path(__file__).parent / "web"


@dataclass(frozen=True)
class Catalog:
    """What the operator page needs before any model loads: machines, manual PDFs and the models in use."""
    machines: list[dict] = field(default_factory=list)
    manual_files: dict[str, Path] = field(default_factory=dict)
    engine: dict[str, str | None] = field(default_factory=dict)


class DiagnoseRequest(BaseModel):
    query: str = Field(max_length=2000, description="The operator's description or fault code.")
    machine_id: str | None = Field(default=None, description="Restricts sources to this machine's manual.")
    language: Literal["auto", "en", "hi", "ta"] = Field(
        default="auto", description="Answer language; auto answers in the question's language.")

    @property
    def answer_language(self) -> str | None:
        return None if self.language == "auto" else self.language

    @field_validator("query")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("query must not be empty")
        if _CONTROL_RE.search(value):
            raise ValueError("query must not contain control characters")
        return value


def create_app(service_factory: Callable[[], object], catalog: Catalog | None = None) -> FastAPI:
    app = FastAPI(title="FaultSense", version="0.1.0",
                  description="Altivar drive diagnostic assistant (Phase 1: English text).")
    holder: dict[str, object] = {}
    catalog = catalog or Catalog()
    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    @app.middleware("http")
    async def revalidate_page_files(request, call_next):
        response = await call_next(request)
        if request.url.path == "/" or request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"  # browsers re-check, so an update shows on reload
        return response

    @app.get("/", include_in_schema=False)
    def page() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html", media_type="text/html")

    @app.get("/info")
    def info() -> dict:
        return {"machines": catalog.machines, "engine": catalog.engine,
                "manuals": sorted(catalog.manual_files)}

    @app.get("/manuals/{manual_id}.pdf", include_in_schema=False)
    def manual_pdf(manual_id: str) -> FileResponse:
        path = catalog.manual_files.get(manual_id)  # only catalogued manuals, so no path traversal
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail=f"Manual {manual_id!r} is not available")
        return FileResponse(path, media_type="application/pdf")

    def service():
        if "service" not in holder:  # models load on the first request, not at import
            holder["service"] = service_factory()
        return holder["service"]

    @app.post("/diagnose", response_model=DiagnosisResponse)
    def diagnose(request: DiagnoseRequest) -> DiagnosisResponse:
        try:
            return service().diagnose(request.query, request.machine_id, language=request.answer_language)
        except UnknownMachine as exc:
            raise HTTPException(status_code=404, detail=f"Unknown machine_id {exc.machine_id!r}") from exc

    @app.post("/diagnose/stream")
    def diagnose_stream(request: DiagnoseRequest) -> StreamingResponse:
        """The same diagnosis, as newline-delimited JSON: stage events while it works, then the result."""
        events: queue.Queue = queue.Queue()

        def work() -> None:
            try:
                response = service().diagnose(
                    request.query, request.machine_id,
                    progress=lambda stage, detail: events.put({"event": "stage", "stage": stage, **detail}),
                    language=request.answer_language)
                events.put({"event": "result", "response": response.model_dump(mode="json")})
            except UnknownMachine as exc:
                events.put({"event": "error", "status": 404, "detail": f"Unknown machine_id {exc.machine_id!r}"})
            except Exception as exc:  # reported in the stream; the HTTP status is already 200
                events.put({"event": "error", "status": 500, "detail": type(exc).__name__})
            finally:
                events.put(None)

        threading.Thread(target=work, daemon=True).start()

        def lines():
            while (item := events.get()) is not None:
                yield json.dumps(item) + "\n"

        return StreamingResponse(lines(), media_type="application/x-ndjson")

    @app.get("/passages/{chunk_id}")
    def passage(chunk_id: str) -> dict:
        found = service().passage(chunk_id)
        if found is None:
            raise HTTPException(status_code=404, detail=f"No manual passage {chunk_id!r}")
        return found

    @app.get("/health")
    def health() -> JSONResponse:
        # 503 lets a load balancer or monitor see that diagnoses would fail right now.
        try:
            report = service().health()
        except Exception as exc:  # the service could not start, e.g. the database refused the connection
            return JSONResponse({"status": "unavailable", "error": type(exc).__name__}, status_code=503)
        if report.get("database", "ok") != "ok":
            return JSONResponse({"status": "degraded", **report}, status_code=503)
        return JSONResponse({"status": "ok", **report})

    return app
