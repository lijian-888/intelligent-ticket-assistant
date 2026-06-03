from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Iterable

from app.models import SupplementTask, TicketStatus


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "demo.db"


def get_connection() -> sqlite3.Connection:
    """创建 SQLite 连接，并启用按字段名读取行数据。"""

    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """初始化 demo 数据库表。"""

    with get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS supplement_tasks (
                ticket_no TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                complainant_name TEXT NOT NULL,
                contact_phone TEXT NOT NULL,
                missing_fields TEXT NOT NULL,
                recommended_supplement_fields TEXT NOT NULL,
                call_script TEXT NOT NULL,
                priority TEXT NOT NULL,
                reason TEXT NOT NULL,
                source_status TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def save_supplement_task(task: SupplementTask) -> SupplementTask:
    """新增或更新补充信息任务。"""

    init_db()
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO supplement_tasks (
                ticket_no,
                title,
                complainant_name,
                contact_phone,
                missing_fields,
                recommended_supplement_fields,
                call_script,
                priority,
                reason,
                source_status,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(ticket_no) DO UPDATE SET
                title = excluded.title,
                complainant_name = excluded.complainant_name,
                contact_phone = excluded.contact_phone,
                missing_fields = excluded.missing_fields,
                recommended_supplement_fields = excluded.recommended_supplement_fields,
                call_script = excluded.call_script,
                priority = excluded.priority,
                reason = excluded.reason,
                source_status = excluded.source_status,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                task.ticket_no,
                task.title,
                task.complainant_name,
                task.contact_phone,
                json.dumps(task.missing_fields, ensure_ascii=False),
                json.dumps(task.recommended_supplement_fields, ensure_ascii=False),
                task.call_script,
                task.priority,
                task.reason,
                task.source_status.value,
            ),
        )
    return task


def list_supplement_tasks_from_db() -> list[SupplementTask]:
    """从数据库读取全部补充信息任务。"""

    init_db()
    with get_connection() as conn:
        rows: Iterable[sqlite3.Row] = conn.execute(
            "SELECT * FROM supplement_tasks ORDER BY updated_at DESC"
        ).fetchall()
    return [_row_to_task(row) for row in rows]


def get_db_status() -> dict[str, object]:
    """返回 demo 数据库位置和关键表行数，便于接口调试和演示排查。"""

    init_db()
    with get_connection() as conn:
        supplement_task_count = conn.execute("SELECT COUNT(*) FROM supplement_tasks").fetchone()[0]
    return {
        "type": "sqlite",
        "path": str(DB_PATH),
        "exists": DB_PATH.exists(),
        "supplement_task_count": supplement_task_count,
    }


def _row_to_task(row: sqlite3.Row) -> SupplementTask:
    """把数据库行转换为接口模型。"""

    return SupplementTask(
        ticket_no=row["ticket_no"],
        title=row["title"],
        complainant_name=row["complainant_name"],
        contact_phone=row["contact_phone"],
        missing_fields=json.loads(row["missing_fields"]),
        recommended_supplement_fields=json.loads(row["recommended_supplement_fields"]),
        call_script=row["call_script"],
        priority=row["priority"],
        reason=row["reason"],
        source_status=TicketStatus(row["source_status"]),
    )
