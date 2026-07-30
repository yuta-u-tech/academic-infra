"""ローカル学習コックピットの API。127.0.0.1 にのみバインドする。

外部公開しない・認証を持たない設計なので、バインド先の誤りがそのまま
「認証なしの個人学習データを LAN に晒す」事故になる。`ensure_loopback()` が
起動前に必ず弾き、テストでもそれを固定している。
"""

from __future__ import annotations

import ipaddress
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import promote, study
from .db import connect
from .model import due_items
from .target import COURSES_YML_PATH

WEB_DIR = Path(__file__).resolve().parent.parent.parent / "web"

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8791  # gjp web(8765) / pm-agent dashboard(4783) と衝突しない番号


class NonLoopbackBindError(Exception):
    pass


def ensure_loopback(host: str) -> str:
    """ループバック以外へのバインドを拒否する。"""
    if host in {"localhost"}:
        return host
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise NonLoopbackBindError(
            f"host={host!r} は解釈できません。127.0.0.1 を使ってください。"
        ) from error
    if not address.is_loopback:
        raise NonLoopbackBindError(
            f"host={host!r} へのバインドは許可されていません"
            "（この UI は認証を持たないため 127.0.0.1 専用です）。"
        )
    return host


class AnswerRequest(BaseModel):
    session_id: int
    item_id: int
    response: str
    elapsed_ms: int = Field(ge=0)
    self_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    hint_used: bool = False
    retry_count: int = Field(default=0, ge=0)
    cause_override: str | None = None


class SessionRequest(BaseModel):
    course_id: str
    note: str | None = None


def create_app(db_path: Path | None = None) -> FastAPI:
    app = FastAPI(title="Academic-Infra English", docs_url=None, redoc_url=None)

    @contextmanager
    def db() -> Iterator[sqlite3.Connection]:
        # sqlite3.Connection 自身の with は commit するだけで閉じない。
        # リクエストごとに開くので、閉じないと接続が溜まる。
        connection = connect(db_path)
        try:
            yield connection
        finally:
            connection.close()

    @app.get("/api/health")
    def health() -> dict:
        with db() as connection:
            version = connection.execute(
                "SELECT MAX(version) AS v FROM schema_migrations"
            ).fetchone()["v"]
        return {"status": "ok", "schema_version": version}

    @app.get("/api/courses")
    def courses() -> dict:
        data = yaml.safe_load(COURSES_YML_PATH.read_text(encoding="utf-8")) or {}
        return {
            "courses": [
                {"course_id": cid, "course_name": entry.get("course_name", cid)}
                for cid, entry in (data.get("courses") or {}).items()
            ]
        }

    @app.post("/api/sessions")
    def create_session(request: SessionRequest) -> dict:
        with db() as connection:
            return {"session_id": study.start_session(connection, request.course_id, request.note)}

    @app.post("/api/sessions/{session_id}/end")
    def finish_session(session_id: int) -> dict:
        with db() as connection:
            study.end_session(connection, session_id)
        return {"session_id": session_id, "ended": True}

    @app.get("/api/queue")
    def queue(course: str | None = None, limit: int = 20) -> dict:
        with db() as connection:
            rows = due_items(connection, course, limit)
            return {"items": [study.item_for_ui(connection, row["id"]) for row in rows]}

    @app.post("/api/answer")
    def answer(request: AnswerRequest) -> dict:
        with db() as connection:
            try:
                outcome = study.answer(
                    connection,
                    session_id=request.session_id,
                    item_id=request.item_id,
                    response=request.response,
                    elapsed_ms=request.elapsed_ms,
                    self_confidence=request.self_confidence,
                    hint_used=request.hint_used,
                    retry_count=request.retry_count,
                    cause_override=request.cause_override,
                )
            except LookupError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
            _, item = study.load_item(connection, request.item_id)

        return {
            "attempt_id": outcome.attempt_id,
            "correct": outcome.correct,
            "error_cause": outcome.error_cause,
            "next_action": outcome.next_action,
            "mastery": outcome.skill_state["mastery"],
            "next_review": outcome.review["next_review"],
            "interval_days": outcome.review["interval"],
            "revision_candidate_id": outcome.revision_candidate_id,
            "explanation": getattr(item, "explanation", None),
            "answer": getattr(item, "word", None)
            or (item.choices[item.answer_index] if hasattr(item, "choices") else None),
        }

    @app.get("/api/candidates")
    def candidates(course: str | None = None) -> dict:
        with db() as connection:
            return {"candidates": promote.open_candidates(connection, course)}

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    return app


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, db_path: Path | None = None) -> None:
    import uvicorn

    uvicorn.run(create_app(db_path), host=ensure_loopback(host), port=port)
