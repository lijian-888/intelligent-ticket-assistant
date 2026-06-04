from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from app.db import get_db_status, init_db
from app.embedding_client import get_embedding_config_status
from app.graph import process_ticket, process_ticket_steps
from app.legal_kb import get_legal_retrieval_config_status
from app.llm_client import get_llm_config_status, ping_llm
from app.mock_data import MOCK_TICKETS
from app.models import ProcessingResult, SupplementTask, Ticket
from app.reranker_client import get_reranker_config_status
from app.smart_transfer import smart_transfer_ticket
from app.supplement import create_or_update_supplement_task, list_saved_supplement_tasks


def create_app() -> FastAPI:
    """创建 FastAPI 应用并注册 demo 接口。"""

    app = FastAPI(title="市场监管投诉举报工单 LangGraph Demo")
    web_dir = Path(__file__).resolve().parent.parent / "web"
    app.mount("/demo", StaticFiles(directory=web_dir, html=True), name="demo")

    @app.on_event("startup")
    def startup() -> None:
        """启动时初始化 demo 数据库。"""

        init_db()

    @app.get("/")
    def root() -> dict[str, Any]:
        """接口首页，返回 demo 名称、当前时间和可用接口列表。"""

        return {
            "name": "市场监管投诉举报工单 LangGraph Demo",
            "time": datetime.now().isoformat(timespec="seconds"),
            "docs": "/docs",
            "demo": "/demo",
            "openapi": "/openapi.json",
            "endpoints": [
                "GET /tickets",
                "GET /tickets/{ticket_no}",
                "POST /tickets/{ticket_no}/process",
                "POST /tickets/{ticket_no}/smart-transfer",
                "POST /tickets/{ticket_no}/process/steps",
                "POST /tickets/{ticket_no}/supplement-task",
                "GET /supplement-tasks",
                "GET /db/status",
                "GET /llm/config",
                "GET /llm/health",
                "GET /embedding/config",
                "GET /retrieval/config",
                "POST /process-all",
            ],
        }

    @app.get("/tickets", response_model=list[Ticket])
    def list_tickets() -> list[Ticket]:
        """模拟获取待处理工单列表，后续可替换为真实工单系统查询接口。"""

        return MOCK_TICKETS

    @app.get("/tickets/{ticket_no}", response_model=Ticket)
    def get_ticket(ticket_no: str) -> Ticket:
        """模拟获取单个工单详情，真实环境中对应工单详情接口。"""

        try:
            return get_mock_ticket(ticket_no)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="工单不存在") from exc

    @app.post("/tickets/{ticket_no}/process", response_model=ProcessingResult)
    def process_one(ticket_no: str) -> ProcessingResult:
        """处理指定工单，并返回结构化、分派、风险和动作建议。"""

        try:
            ticket = get_mock_ticket(ticket_no)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="工单不存在") from exc
        return process_ticket(ticket)

    @app.post("/tickets/{ticket_no}/smart-transfer", response_model=ProcessingResult)
    def smart_transfer_one(ticket_no: str) -> ProcessingResult:
        """智能流转指定工单：高置信度自动执行，低置信度只返回推荐动作。"""

        try:
            ticket = get_mock_ticket(ticket_no)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="工单不存在") from exc
        return smart_transfer_ticket(ticket)

    @app.post("/tickets/{ticket_no}/process/steps")
    def process_one_steps(ticket_no: str) -> list[dict[str, Any]]:
        """处理指定工单，并返回 LangGraph 每个节点的中间输出。"""

        try:
            ticket = get_mock_ticket(ticket_no)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="工单不存在") from exc
        return process_ticket_steps(ticket)

    @app.post("/tickets/{ticket_no}/supplement-task", response_model=SupplementTask)
    def create_supplement_task(ticket_no: str) -> SupplementTask:
        """为缺失核心字段的工单生成电话补充任务。"""

        try:
            ticket = get_mock_ticket(ticket_no)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="工单不存在") from exc
        task = create_or_update_supplement_task(ticket)
        if task is None:
            raise HTTPException(status_code=400, detail="该工单没有核心字段缺失，不需要生成补充任务")
        return task

    @app.get("/supplement-tasks", response_model=list[SupplementTask])
    def list_supplement_tasks() -> list[SupplementTask]:
        """查看已经生成的电话核实补充信息任务。"""

        return list_saved_supplement_tasks()

    @app.get("/db/status")
    def db_status() -> dict[str, object]:
        """查看当前 demo 数据库路径和补充任务表数量。"""

        return get_db_status()

    @app.get("/llm/config")
    def llm_config() -> dict[str, Any]:
        """查看脱敏后的大模型配置状态，用于排查环境变量是否生效。"""

        return get_llm_config_status()

    @app.get("/llm/health")
    def llm_health() -> dict[str, Any]:
        """用短 prompt 测试大模型接口是否可用。"""

        try:
            return ping_llm()
        except Exception as exc:
            return {
                "ok": False,
                "error": f"{type(exc).__name__}: {exc}",
                "config": get_llm_config_status(),
            }

    @app.get("/embedding/config")
    def embedding_config() -> dict[str, Any]:
        """查看脱敏后的向量模型配置状态，用于确认 bge-m3 地址是否生效。"""

        return get_embedding_config_status()

    @app.get("/retrieval/config")
    def retrieval_config() -> dict[str, Any]:
        """查看法律条款混合检索配置，包括 embedding、reranker 和阈值。"""

        return {
            "legal_retrieval": get_legal_retrieval_config_status(),
            "embedding": get_embedding_config_status(),
            "reranker": get_reranker_config_status(),
        }

    @app.post("/process-all", response_model=list[ProcessingResult])
    def process_all() -> list[ProcessingResult]:
        """批量处理当前 mock 列表中的所有工单，便于 demo 演示整体效果。"""

        return [process_ticket(ticket) for ticket in MOCK_TICKETS]

    return app


def get_mock_ticket(ticket_no: str) -> Ticket:
    """从模拟工单列表中按工单编号查找单条工单。"""

    for ticket in MOCK_TICKETS:
        if ticket.ticket_no == ticket_no:
            return ticket
    raise KeyError(ticket_no)
