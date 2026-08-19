"""ローカル学習コックピットの API。127.0.0.1 にのみバインドする。

外部公開しない・認証を持たない設計なので、バインド先の誤りがそのまま
「認証なしの個人学習データを LAN に晒す」事故になる。`ensure_loopback()` が
起動前に必ず弾き、テストでもそれを固定している。
"""

from __future__ import annotations

import ipaddress
import random
import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import dashboard, promote, study
from .db import connect
from .model import due_items
from .target import COURSES_YML_PATH

if getattr(sys, "frozen", False):
    # PyInstaller sidecar (desktop/): データは _MEIPASS 直下に web/ として同梱される。
    WEB_DIR = Path(sys._MEIPASS) / "web"  # type: ignore[attr-defined]
else:
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
    correct_override: bool | None = None


class GradeRequest(BaseModel):
    attempt_id: int
    grade: int = Field(ge=0, le=3, description="0=もう一度 1=難しい 2=普通 3=簡単")


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
        """科目 + 取り込み済みの外部素材。

        外部素材（TOEIC/VOA/TED）は `courses.yml` に載らないので、実際に取り込まれた
        ものだけを DB から拾って足す。出題できるものだけが選択肢に出る。
        """
        data = yaml.safe_load(COURSES_YML_PATH.read_text(encoding="utf-8")) or {}
        listed = [
            {"course_id": cid, "course_name": entry.get("course_name", cid)}
            for cid, entry in (data.get("courses") or {}).items()
        ]
        known = {c["course_id"] for c in listed}

        with db() as connection:
            rows = connection.execute(
                "SELECT DISTINCT course_id, source FROM material WHERE source != 'academic'"
            ).fetchall()
        for row in rows:
            if row["course_id"] in known:
                continue
            known.add(row["course_id"])
            listed.insert(0, {"course_id": row["course_id"], "course_name": "英語（一般・TOEIC）"})
        return {"courses": listed}

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
    def queue(
        course: str | None = None,
        limit: int = 20,
        kinds: str | None = None,
        exclude: str | None = None,
        vocab_direction: str | None = None,
    ) -> dict:
        """出題キュー。`exclude` は同一セッションで解き終えた item_id（再出題しない）。

        `vocab_direction` に `recall`/`recognition` を渡すと、語彙をその方向だけに絞る
        （未指定なら従来通り両方向を混ぜる。語彙以外の種別には影響しない）。
        """
        wanted = [k.strip() for k in kinds.split(",") if k.strip()] if kinds else None
        answered = {int(i) for i in exclude.split(",") if i.strip().isdigit()} if exclude else set()

        with db() as connection:
            # 解き終えた分を差し引いても補充できるよう、多めに引いてから間引く。
            rows = due_items(
                connection, course, limit + len(answered), wanted,
                vocab_direction=vocab_direction or None,
            )
            fresh = [row for row in rows if row["id"] not in answered][:limit]
            # due_items() は未出題を gi.id（=投入順）のまま返すため、単語帳の並びで
            # 隣接登録された類語（assure/ensure/insure 等）が連続して出てしまい、
            # 前の問題が次の問題のヒントになる。復習優先の選定自体は due_items() 側で
            # 既に済んでいるので、ここでは提示順だけをシャッフルする。
            random.shuffle(fresh)
            return {"items": [study.item_for_ui(connection, row["id"]) for row in fresh]}

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
                    correct_override=request.correct_override,
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
            # 出題中は伏せていた用例・コロケーションは、ここで定着のために見せる。
            "example": getattr(item, "example", None),
            "collocations": getattr(item, "collocations", None) or None,
        }

    @app.get("/api/hint")
    def hint(item_id: int) -> dict:
        """語彙の頭文字ヒント。

        クライアントで持たせず毎回サーバーに取りに来させるのは、`hint_used` を
        自己申告に頼らないため。ヒントを見たかどうかは習熟度の計算に効く。
        """
        with db() as connection:
            try:
                _, item = study.load_item(connection, item_id)
            except LookupError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
        if not hasattr(item, "word") or item.sub_skill == "recognition":
            raise HTTPException(status_code=422, detail="この種別にヒントはありません。")
        return {"hint": study.hint_for(item.word)}

    @app.get("/api/reveal")
    def reveal(item_id: int) -> dict:
        """語彙フラッシュカードの答えを自己採点の直前に開示する。"""
        with db() as connection:
            try:
                _, item = study.load_item(connection, item_id)
            except LookupError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
        if not hasattr(item, "word") or item.sub_skill not in {"recall", "recognition"}:
            raise HTTPException(status_code=422, detail="このカードは開示式ではありません。")
        return {"word": item.word, "meaning": item.meaning, "example": item.example,
                "collocations": item.collocations}

    @app.post("/api/grade")
    def set_grade(request: GradeRequest) -> dict:
        """答えを見たあとの手応え。復習間隔を引き直す（mastery は動かさない）。"""
        with db() as connection:
            try:
                review = study.grade(connection, request.attempt_id, request.grade)
            except LookupError as error:
                raise HTTPException(status_code=404, detail=str(error)) from error
            except ValueError as error:
                raise HTTPException(status_code=422, detail=str(error)) from error
        return {"interval_days": review["interval"], "next_review": review["next_review"]}

    @app.get("/api/candidates")
    def candidates(course: str | None = None) -> dict:
        with db() as connection:
            return {"candidates": promote.open_candidates(connection, course)}

    @app.get("/api/dashboard")
    def get_dashboard(course_id: str) -> dict:
        with db() as connection:
            return dashboard.build_dashboard(connection, course_id)

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

    return app


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, db_path: Path | None = None) -> None:
    import uvicorn

    uvicorn.run(create_app(db_path), host=ensure_loopback(host), port=port)
