from __future__ import annotations

import os
import math
from dataclasses import dataclass
from typing import Any

import requests
from dotenv import load_dotenv


load_dotenv()
load_dotenv(".env.example", override=False)

RERANKER_BASE_URL = os.getenv("RERANKER_BASE_URL", "").rstrip("/")
RERANKER_API_KEY = os.getenv("RERANKER_API_KEY", "")
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "bge-reranker-v2-m3")
RERANKER_TIMEOUT_SECONDS = float(os.getenv("RERANKER_TIMEOUT_SECONDS", "30"))
_LAST_RERANKER_ERROR = ""
_LAST_RERANKER_SOURCE = "disabled"


@dataclass(frozen=True)
class RerankResult:
    """reranker 对单个候选文档的重排结果。"""

    index: int
    score: float


def is_reranker_configured() -> bool:
    """判断是否配置了 reranker 服务地址。"""

    return bool(RERANKER_BASE_URL)


def get_reranker_config_status() -> dict[str, Any]:
    """返回脱敏后的 reranker 配置状态。"""

    return {
        "configured": is_reranker_configured(),
        "base_url": RERANKER_BASE_URL,
        "model": RERANKER_MODEL,
        "timeout_seconds": RERANKER_TIMEOUT_SECONDS,
        "api_key_set": bool(RERANKER_API_KEY),
        "last_reranker_source": _LAST_RERANKER_SOURCE,
        "last_error": _LAST_RERANKER_ERROR,
    }


def rerank_documents(query: str, documents: list[str], top_n: int) -> list[RerankResult]:
    """调用 OpenAI-compatible rerank 接口；失败时返回空列表，由上游回退向量分数。"""

    global _LAST_RERANKER_ERROR, _LAST_RERANKER_SOURCE
    if not query or not documents or not is_reranker_configured():
        _LAST_RERANKER_SOURCE = "disabled"
        _LAST_RERANKER_ERROR = ""
        return []
    try:
        results = _rerank_documents_remote(query, documents, top_n)
        _LAST_RERANKER_SOURCE = "remote"
        _LAST_RERANKER_ERROR = ""
        return results
    except Exception as exc:
        _LAST_RERANKER_SOURCE = "fallback_vector_score"
        _LAST_RERANKER_ERROR = f"{type(exc).__name__}: {exc}"
        return []


def _rerank_documents_remote(query: str, documents: list[str], top_n: int) -> list[RerankResult]:
    """调用 rerank 接口，并兼容 /v1/rerank 与 /rerank 两种常见路径。"""

    headers = {"Content-Type": "application/json"}
    if RERANKER_API_KEY:
        headers["Authorization"] = f"Bearer {RERANKER_API_KEY}"
    payload = {
        "model": RERANKER_MODEL,
        "query": query,
        "documents": documents,
        "top_n": top_n,
    }

    last_response = None
    for endpoint in _candidate_rerank_endpoints():
        response = requests.post(
            endpoint,
            headers=headers,
            json=payload,
            timeout=RERANKER_TIMEOUT_SECONDS,
        )
        if response.status_code != 404:
            response.raise_for_status()
            return _parse_rerank_response(response.json())
        last_response = response
    response = last_response
    if response is None:
        raise RuntimeError("未生成 reranker 请求地址")
    response.raise_for_status()
    return []


def _candidate_rerank_endpoints() -> list[str]:
    """根据配置地址生成候选 reranker 路径。"""

    if RERANKER_BASE_URL.endswith("/v1"):
        root = RERANKER_BASE_URL[:-3]
        return [f"{RERANKER_BASE_URL}/rerank", f"{root}/rerank"]
    return [f"{RERANKER_BASE_URL}/v1/rerank", f"{RERANKER_BASE_URL}/rerank"]


def _parse_rerank_response(body: dict[str, Any]) -> list[RerankResult]:
    """解析 reranker 返回值，支持 results/data/scores 三类常见格式。"""

    if isinstance(body.get("scores"), list):
        return [
            RerankResult(index=index, score=float(score))
            for index, score in enumerate(body["scores"])
        ]

    raw_results = body.get("results") or body.get("data") or []
    parsed = []
    for position, item in enumerate(raw_results):
        index = item.get("index", position)
        score = item.get("relevance_score", item.get("score", item.get("similarity", 0.0)))
        parsed.append(RerankResult(index=int(index), score=_normalize_score(float(score))))
    return parsed


def _normalize_score(score: float) -> float:
    """把 reranker 原始分数转换到 0-1，便于配置统一阈值。"""

    if 0.0 <= score <= 1.0:
        return score
    return 1.0 / (1.0 + math.exp(-score))
