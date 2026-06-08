from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import dotenv_values, load_dotenv

from app.embedding_client import embed_texts, get_embedding_runtime_model
from app.legal_docx_parser import ParsedLegalDocument, parse_legal_docx_directory
from app.models import LegalReference
from app.reranker_client import get_reranker_runtime_model, rerank_documents


load_dotenv()
load_dotenv(".env.example", override=False)


@dataclass(frozen=True)
class LegalPgConfig:
    """真实法律知识库运行配置。"""

    backend: str
    database_url: str
    import_batch_size: int
    vector_top_k: int
    keyword_top_k: int
    display_top_k: int
    min_relevance_score: float
    enable_reranker: bool
    enable_keyword_search: bool


@dataclass(frozen=True)
class PgLegalCandidate:
    """从 PostgreSQL 向量召回得到的候选条文。"""

    chunk_key: str
    law_name: str
    chapter: str
    article: str
    chunk_text: str
    embedding_model: str
    vector_score: float
    final_score: float
    keyword_score: float = 0.0
    rerank_score: float = 0.0
    reranker_model: str = ""


def is_pg_legal_kb_configured() -> bool:
    """判断是否配置了 PostgreSQL 法律知识库。"""

    config = read_legal_pg_config()
    return config.backend in {"auto", "postgres"} and bool(config.database_url)


def get_pg_legal_kb_status() -> dict[str, Any]:
    """返回真实法律知识库状态，便于排查是否已连接、是否已导入条文。"""

    config = read_legal_pg_config()
    status: dict[str, Any] = {
        "backend": config.backend,
        "configured": is_pg_legal_kb_configured(),
        "database_url_set": bool(config.database_url),
        "import_batch_size": config.import_batch_size,
        "keyword_top_k": config.keyword_top_k,
        "enable_keyword_search": config.enable_keyword_search,
        "document_count": 0,
        "chunk_count": 0,
        "embedding_models": [],
        "last_error": "",
    }
    if not is_pg_legal_kb_configured():
        return status
    try:
        with _connect() as conn:
            _ensure_schema(conn)
            with conn.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM legal_documents")
                status["document_count"] = cursor.fetchone()[0]
                cursor.execute("SELECT COUNT(*) FROM legal_chunks")
                status["chunk_count"] = cursor.fetchone()[0]
                cursor.execute(
                    """
                    SELECT DISTINCT embedding_model
                    FROM legal_chunks
                    WHERE embedding_model <> ''
                    ORDER BY embedding_model
                    """
                )
                status["embedding_models"] = [row[0] for row in cursor.fetchall()]
        return status
    except Exception as exc:
        status["last_error"] = f"{type(exc).__name__}: {exc}"
        return status


def list_legal_chunks_from_pg(limit: int = 50, offset: int = 0, source_file: str = "") -> dict[str, Any]:
    """分页查看 PostgreSQL 中已经入库的法规切片。"""

    status = get_pg_legal_kb_status()
    if not status["configured"] or status.get("last_error"):
        return {**status, "items": []}
    where_clause = "WHERE is_active = TRUE"
    params: list[Any] = []
    if source_file:
        where_clause += " AND metadata ->> 'source_file' ILIKE %s"
        params.append(f"%{source_file}%")
    with _connect() as conn:
        _ensure_schema(conn)
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT COUNT(*) FROM legal_chunks {where_clause}",
                params,
            )
            filtered_chunk_count = cursor.fetchone()[0]
            cursor.execute(
                """
                SELECT
                    chunk_key,
                    law_name,
                    chapter,
                    article,
                    chunk_text,
                    sequence,
                    embedding_model,
                    embedding_dimension,
                    metadata ->> 'source_file' AS source_file
                FROM legal_chunks
                {where_clause}
                ORDER BY law_name, sequence
                LIMIT %s OFFSET %s
                """.format(where_clause=where_clause),
                [*params, limit, offset],
            )
            rows = cursor.fetchall()
    items = [
        {
            "chunk_key": row[0],
            "law_name": row[1],
            "chapter": row[2],
            "article": row[3],
            "chunk_text": row[4],
            "sequence": row[5],
            "embedding_model": row[6],
            "embedding_dimension": row[7],
            "source_file": row[8] or "",
        }
        for row in rows
    ]
    return {
        **status,
        "filtered_chunk_count": filtered_chunk_count,
        "source_file_filter": source_file,
        "limit": limit,
        "offset": offset,
        "items": items,
    }


def import_legal_docx_directory(directory: Path, rebuild: bool = False) -> dict[str, Any]:
    """解析目录中的法规 docx、doc、pdf，生成向量后持久化到 PostgreSQL + pgvector。"""

    if not is_pg_legal_kb_configured():
        raise RuntimeError("未配置 LEGAL_DATABASE_URL，无法导入真实法律知识库。")
    documents = parse_legal_docx_directory(directory)
    if not documents:
        return {"document_count": 0, "chunk_count": 0, "message": "未发现 docx、doc 或 pdf 文件。"}

    all_chunks = [chunk for document in documents for chunk in document.chunks]
    sample_vector = embed_texts([all_chunks[0].chunk_text])[0] if all_chunks else embed_texts(["法律知识库"])[0]
    embedding_dimension = len(sample_vector)
    embedding_model = get_embedding_runtime_model()

    with _connect() as conn:
        _ensure_schema(conn, embedding_dimension=embedding_dimension)
        if rebuild:
            with conn.cursor() as cursor:
                cursor.execute("DELETE FROM legal_chunks")
                cursor.execute("DELETE FROM legal_documents")
        for document in documents:
            _upsert_document(conn, document, embedding_model, embedding_dimension)

    return {
        "document_count": len(documents),
        "chunk_count": len(all_chunks),
        "embedding_model": embedding_model,
        "embedding_dimension": embedding_dimension,
        "rebuild": rebuild,
    }


def search_legal_references_from_pg(
    query_text: str,
    vector_top_k: int,
    display_top_k: int,
    min_relevance_score: float,
    enable_reranker: bool,
) -> list[LegalReference]:
    """使用 PostgreSQL pgvector 执行真实法律知识库检索。"""

    if not is_pg_legal_kb_configured():
        return []
    query_vector = embed_texts([query_text])[0]
    vector_literal = _vector_literal(query_vector)
    config = read_legal_pg_config()
    with _connect() as conn:
        _ensure_schema(conn, embedding_dimension=len(query_vector))
        vector_candidates = _search_vector_candidates(conn, vector_literal, len(query_vector), vector_top_k)
        keyword_candidates = (
            _search_keyword_candidates(conn, query_text, config.keyword_top_k)
            if config.enable_keyword_search
            else []
        )

    candidates = _merge_candidates(vector_candidates, keyword_candidates)
    if enable_reranker:
        candidates = _rerank_pg_candidates(query_text, candidates, display_top_k)
    return _build_references(candidates, display_top_k, min_relevance_score)


def read_legal_pg_config() -> LegalPgConfig:
    """读取真实法律知识库配置，支持 .env 运行时变更。"""

    values: dict[str, Any] = {}
    values.update(dotenv_values(".env.example"))
    values.update(dotenv_values(".env"))
    for key in (
        "LEGAL_KB_BACKEND",
        "LEGAL_DATABASE_URL",
        "LEGAL_IMPORT_BATCH_SIZE",
        "LEGAL_VECTOR_TOP_K",
        "LEGAL_KEYWORD_TOP_K",
        "LEGAL_DISPLAY_TOP_K",
        "LEGAL_MIN_RELEVANCE_SCORE",
        "LEGAL_ENABLE_RERANKER",
        "LEGAL_ENABLE_KEYWORD_SEARCH",
    ):
        env_value = os.getenv(key)
        if env_value not in (None, ""):
            values[key] = env_value
    return LegalPgConfig(
        backend=str(values.get("LEGAL_KB_BACKEND") or "auto").lower(),
        database_url=str(values.get("LEGAL_DATABASE_URL") or ""),
        import_batch_size=max(1, int(values.get("LEGAL_IMPORT_BATCH_SIZE") or 16)),
        vector_top_k=int(values.get("LEGAL_VECTOR_TOP_K") or 10),
        keyword_top_k=int(values.get("LEGAL_KEYWORD_TOP_K") or 10),
        display_top_k=int(values.get("LEGAL_DISPLAY_TOP_K") or 3),
        min_relevance_score=float(values.get("LEGAL_MIN_RELEVANCE_SCORE") or 0.55),
        enable_reranker=str(values.get("LEGAL_ENABLE_RERANKER") or "true").lower() == "true",
        enable_keyword_search=str(values.get("LEGAL_ENABLE_KEYWORD_SEARCH") or "true").lower() == "true",
    )


def _connect():
    """创建 PostgreSQL 连接；未安装 psycopg 时给出明确错误。"""

    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError("缺少 psycopg 依赖，请先安装 requirements.txt。") from exc
    return psycopg.connect(read_legal_pg_config().database_url)


def _ensure_schema(conn, embedding_dimension: int | None = None) -> None:
    """初始化 pgvector 扩展和法律知识库表。"""

    with conn.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS vector")
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_documents (
                document_key TEXT PRIMARY KEY,
                law_name TEXT NOT NULL,
                revision_note TEXT NOT NULL DEFAULT '',
                source_file TEXT NOT NULL,
                document_type TEXT NOT NULL DEFAULT '法律法规规章',
                status TEXT NOT NULL DEFAULT '有效',
                embedding_model TEXT NOT NULL DEFAULT '',
                embedding_dimension INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS legal_chunks (
                chunk_key TEXT PRIMARY KEY,
                document_key TEXT NOT NULL REFERENCES legal_documents(document_key) ON DELETE CASCADE,
                law_name TEXT NOT NULL,
                chapter TEXT NOT NULL DEFAULT '',
                article TEXT NOT NULL DEFAULT '',
                chunk_text TEXT NOT NULL,
                sequence INTEGER NOT NULL,
                embedding vector,
                embedding_model TEXT NOT NULL,
                embedding_dimension INTEGER NOT NULL,
                is_active BOOLEAN NOT NULL DEFAULT TRUE,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS legal_chunks_document_idx ON legal_chunks(document_key)")
        cursor.execute("CREATE INDEX IF NOT EXISTS legal_chunks_active_idx ON legal_chunks(is_active)")
        cursor.execute("CREATE INDEX IF NOT EXISTS legal_chunks_metadata_idx ON legal_chunks USING GIN(metadata)")
        # 当前法规库规模较小，先使用 pgvector 顺序召回，避免 embedding 维度未稳定时索引创建失败。
        # 后续确认 bge-m3 返回维度后，可再为 embedding 增加 HNSW/IVFFLAT 专用索引。
    conn.commit()


def _search_vector_candidates(conn, vector_literal: str, embedding_dimension: int, vector_top_k: int) -> list[PgLegalCandidate]:
    """用 pgvector 召回语义相近的法律片段。"""

    with conn.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                chunk_key,
                law_name,
                chapter,
                article,
                chunk_text,
                embedding_model,
                1 - (embedding <=> %s::vector) AS vector_score
            FROM legal_chunks
            WHERE is_active = TRUE
                AND embedding_dimension = %s
            ORDER BY embedding <=> %s::vector
            LIMIT %s
            """,
            (vector_literal, embedding_dimension, vector_literal, vector_top_k),
        )
        rows = cursor.fetchall()
    return [
        PgLegalCandidate(
            chunk_key=row[0],
            law_name=row[1],
            chapter=row[2],
            article=row[3],
            chunk_text=row[4],
            embedding_model=row[5],
            vector_score=float(row[6]),
            final_score=float(row[6]),
        )
        for row in rows
        if row[6] is not None and float(row[6]) > 0
    ]


def _search_keyword_candidates(conn, query_text: str, keyword_top_k: int) -> list[PgLegalCandidate]:
    """用关键词短语命中补充召回，解决法律术语、条号和固定表述被向量召回漏掉的问题。"""

    terms = _extract_keyword_terms(query_text)
    if not terms:
        return []
    conditions = []
    where_params: list[Any] = []
    for term in terms:
        conditions.append("(law_name ILIKE %s OR article ILIKE %s OR chunk_text ILIKE %s)")
        like = f"%{term}%"
        where_params.extend([like, like, like])
    score_parts = []
    score_params: list[Any] = []
    for term in terms:
        score_parts.append(
            """
            CASE
                WHEN law_name ILIKE %s THEN 3
                WHEN article ILIKE %s THEN 2
                WHEN chunk_text ILIKE %s THEN 1
                ELSE 0
            END
            """
        )
        like = f"%{term}%"
        score_params.extend([like, like, like])
    params = [*score_params, max(1, len(terms)), *where_params, keyword_top_k]
    sql = f"""
        SELECT
            chunk_key,
            law_name,
            chapter,
            article,
            chunk_text,
            embedding_model,
            ({' + '.join(score_parts)})::float / (%s * 3.0) AS keyword_score
        FROM legal_chunks
        WHERE is_active = TRUE
            AND ({' OR '.join(conditions)})
        ORDER BY keyword_score DESC, sequence ASC
        LIMIT %s
    """
    with conn.cursor() as cursor:
        cursor.execute(sql, params)
        rows = cursor.fetchall()
    return [
        PgLegalCandidate(
            chunk_key=row[0],
            law_name=row[1],
            chapter=row[2],
            article=row[3],
            chunk_text=row[4],
            embedding_model=row[5],
            vector_score=0.0,
            keyword_score=float(row[6] or 0.0),
            final_score=float(row[6] or 0.0),
        )
        for row in rows
        if row[6] is not None and float(row[6]) > 0
    ]


def _merge_candidates(
    vector_candidates: list[PgLegalCandidate],
    keyword_candidates: list[PgLegalCandidate],
) -> list[PgLegalCandidate]:
    """合并语义召回和关键词召回候选，同一 chunk 只保留一条并合并分数。"""

    merged: dict[str, PgLegalCandidate] = {}
    for candidate in [*vector_candidates, *keyword_candidates]:
        existing = merged.get(candidate.chunk_key)
        if existing is None:
            merged[candidate.chunk_key] = candidate
            continue
        merged[candidate.chunk_key] = PgLegalCandidate(
            chunk_key=existing.chunk_key,
            law_name=existing.law_name,
            chapter=existing.chapter,
            article=existing.article,
            chunk_text=existing.chunk_text,
            embedding_model=existing.embedding_model or candidate.embedding_model,
            vector_score=max(existing.vector_score, candidate.vector_score),
            keyword_score=max(existing.keyword_score, candidate.keyword_score),
            final_score=max(existing.final_score, candidate.final_score),
            rerank_score=max(existing.rerank_score, candidate.rerank_score),
            reranker_model=existing.reranker_model or candidate.reranker_model,
        )
    return sorted(
        merged.values(),
        key=lambda item: (max(item.vector_score, item.keyword_score), item.vector_score, item.keyword_score),
        reverse=True,
    )


def _extract_keyword_terms(query_text: str, max_terms: int = 12) -> list[str]:
    """从工单文本中提取适合数据库短语命中的关键词。"""

    normalized = re.sub(r"\s+", " ", query_text)
    terms: list[str] = []
    for token in re.split(r"[，。；、,.!?！？\s（）()]+|未取得|情况下|对外|其中|要求|依法|进行|提供|并|和|的", normalized):
        token = token.strip()
        if len(token) < 2 or token.isdigit():
            continue
        if _is_low_value_keyword(token):
            continue
        terms.append(token)
    for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,12}", normalized):
        if len(token) < 2 or token.isdigit():
            continue
        if _is_low_value_keyword(token):
            continue
        terms.append(token)
    deduped = []
    seen = set()
    for term in terms:
        if term not in seen:
            seen.add(term)
            deduped.append(term)
        if len(deduped) >= max_terms:
            break
    return deduped


def _is_low_value_keyword(term: str) -> bool:
    """过滤过于通用、对法律条文召回帮助不大的短词。"""

    stop_words = {
        "提交人",
        "要求",
        "部门",
        "处理",
        "核查",
        "查处",
        "北京市",
        "北京市朝阳区",
        "市场监管",
        "工作人员",
        "工单",
        "服务",
        "反映",
    }
    return term in stop_words or len(term) > 24


def _upsert_document(
    conn,
    document: ParsedLegalDocument,
    embedding_model: str,
    embedding_dimension: int,
) -> None:
    """写入单个法规文档及其条文切片；重复导入时覆盖同一文档切片。"""

    with conn.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO legal_documents (
                document_key,
                law_name,
                revision_note,
                source_file,
                embedding_model,
                embedding_dimension,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT(document_key) DO UPDATE SET
                law_name = excluded.law_name,
                revision_note = excluded.revision_note,
                source_file = excluded.source_file,
                embedding_model = excluded.embedding_model,
                embedding_dimension = excluded.embedding_dimension,
                updated_at = NOW()
            """,
            (
                document.document_key,
                document.law_name,
                document.revision_note,
                document.source_file,
                embedding_model,
                embedding_dimension,
            ),
        )
        cursor.execute("DELETE FROM legal_chunks WHERE document_key = %s", (document.document_key,))

    config = read_legal_pg_config()
    for batch_start in range(0, len(document.chunks), config.import_batch_size):
        batch = document.chunks[batch_start : batch_start + config.import_batch_size]
        vectors = embed_texts([_chunk_embedding_text(chunk.chunk_text, document.law_name) for chunk in batch])
        runtime_model = get_embedding_runtime_model()
        with conn.cursor() as cursor:
            for chunk, vector in zip(batch, vectors):
                cursor.execute(
                    """
                    INSERT INTO legal_chunks (
                        chunk_key,
                        document_key,
                        law_name,
                        chapter,
                        article,
                        chunk_text,
                        sequence,
                        embedding,
                        embedding_model,
                        embedding_dimension,
                        metadata,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s::vector, %s, %s, %s::jsonb, NOW())
                    """,
                    (
                        chunk.chunk_key,
                        document.document_key,
                        chunk.law_name,
                        chunk.chapter,
                        chunk.article,
                        chunk.chunk_text,
                        chunk.sequence,
                        _vector_literal(vector),
                        runtime_model,
                        len(vector),
                        json.dumps(
                            {
                                "source_file": chunk.source_file,
                                "revision_note": document.revision_note,
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
        conn.commit()


def _rerank_pg_candidates(
    query_text: str,
    candidates: list[PgLegalCandidate],
    display_top_k: int,
) -> list[PgLegalCandidate]:
    """使用 reranker 对真实知识库召回结果重排。"""

    if not candidates:
        return candidates
    documents = [
        f"{candidate.law_name} {candidate.chapter} {candidate.article}\n{candidate.chunk_text}"
        for candidate in candidates
    ]
    reranked = rerank_documents(query_text, documents, top_n=min(len(candidates), display_top_k))
    if not reranked:
        return candidates
    candidate_by_index = {index: candidate for index, candidate in enumerate(candidates)}
    updated = []
    for item in reranked:
        candidate = candidate_by_index.get(item.index)
        if candidate is None:
            continue
        updated.append(
            PgLegalCandidate(
                chunk_key=candidate.chunk_key,
                law_name=candidate.law_name,
                chapter=candidate.chapter,
                article=candidate.article,
                chunk_text=candidate.chunk_text,
                embedding_model=candidate.embedding_model,
                vector_score=candidate.vector_score,
                keyword_score=candidate.keyword_score,
                final_score=item.score,
                rerank_score=item.score,
                reranker_model=get_reranker_runtime_model(),
            )
        )
    return updated or candidates


def _build_references(
    candidates: list[PgLegalCandidate],
    display_top_k: int,
    min_relevance_score: float,
) -> list[LegalReference]:
    """把真实知识库候选条文转换为接口返回模型。"""

    references: list[LegalReference] = []
    for candidate in sorted(candidates, key=lambda item: item.final_score, reverse=True):
        if candidate.final_score < min_relevance_score:
            continue
        references.append(
            LegalReference(
                law_name=candidate.law_name,
                article=candidate.article,
                excerpt=_short_excerpt(candidate.chunk_text),
                relevance_score=round(candidate.final_score, 2),
                reason="真实法律知识库向量检索命中该条文；已按相关性阈值过滤。",
                retrieval_method=_retrieval_method(candidate),
                embedding_model=candidate.embedding_model,
                reranker_model=candidate.reranker_model,
                vector_score=round(candidate.vector_score, 2),
                keyword_score=round(candidate.keyword_score, 2),
                rerank_score=round(candidate.rerank_score, 2),
                source_id=candidate.chunk_key,
            )
        )
        if len(references) >= display_top_k:
            break
    return references


def _chunk_embedding_text(chunk_text: str, law_name: str) -> str:
    """组合条文上下文，提升 embedding 对法律名称和条文内容的感知。"""

    return f"{law_name}\n{chunk_text}"


def _retrieval_method(candidate: PgLegalCandidate) -> str:
    """根据候选来源标识检索方式，便于接口结果说明是否经过混合召回和重排。"""

    has_vector = candidate.vector_score > 0
    has_keyword = candidate.keyword_score > 0
    has_rerank = candidate.rerank_score > 0
    if has_vector and has_keyword and has_rerank:
        return "hybrid_vector_keyword_rerank"
    if has_keyword and has_rerank:
        return "keyword_rerank"
    if has_vector and has_rerank:
        return "pgvector_rerank"
    if has_vector and has_keyword:
        return "hybrid_vector_keyword"
    if has_keyword:
        return "keyword"
    return "pgvector"


def _short_excerpt(text: str, max_length: int = 180) -> str:
    """生成展示给工作人员的短摘录。"""

    compact = " ".join(text.split())
    if len(compact) <= max_length:
        return compact
    return compact[:max_length] + "..."


def _vector_literal(vector: list[float]) -> str:
    """把 Python 向量转换为 pgvector 可接受的文本字面量。"""

    return "[" + ",".join(str(float(value)) for value in vector) + "]"
