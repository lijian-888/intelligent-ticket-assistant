from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

from app.embedding_client import cosine_similarity, embed_texts, get_embedding_runtime_model
from app.models import LegalReference, StructuredTicket, Ticket
from app.reranker_client import get_reranker_runtime_model, rerank_documents


load_dotenv()
load_dotenv(".env.example", override=False)

LEGAL_VECTOR_TOP_K = int(os.getenv("LEGAL_VECTOR_TOP_K", "10"))
LEGAL_DISPLAY_TOP_K = int(os.getenv("LEGAL_DISPLAY_TOP_K", "3"))
LEGAL_MIN_RELEVANCE_SCORE = float(os.getenv("LEGAL_MIN_RELEVANCE_SCORE", "0.55"))
LEGAL_ENABLE_RERANKER = os.getenv("LEGAL_ENABLE_RERANKER", "true").lower() == "true"
LEGAL_PREWARM_ON_STARTUP = os.getenv("LEGAL_PREWARM_ON_STARTUP", "true").lower() == "true"


@dataclass(frozen=True)
class LegalArticle:
    """mock 法律知识库条目；系统启动后会转成向量索引。"""

    source_id: str
    law_name: str
    article: str
    excerpt: str
    retrieval_text: str
    reason_template: str


@dataclass(frozen=True)
class LegalVectorEntry:
    """法律条款向量索引中的单条记录。"""

    article: LegalArticle
    vector: list[float]
    embedding_model: str


@dataclass(frozen=True)
class LegalCandidate:
    """向量召回后的候选法条，后续可进入 reranker 重排。"""

    entry: LegalVectorEntry
    vector_score: float
    final_score: float
    rerank_score: float = 0.0
    reranker_model: str = ""


LEGAL_KNOWLEDGE_BASE: tuple[LegalArticle, ...] = (
    LegalArticle(
        source_id="consumer_law_55",
        law_name="中华人民共和国消费者权益保护法",
        article="第五十五条",
        excerpt="经营者提供商品或者服务有欺诈行为的，消费者可以依法主张增加赔偿。",
        retrieval_text="消费者权益保护 欺诈 消费纠纷 退款 退货 赔偿 协调 消费者 商品 服务",
        reason_template="向量检索显示该工单与消费者权益、退款赔偿或欺诈争议语义接近。",
    ),
    LegalArticle(
        source_id="advertising_law_28",
        law_name="中华人民共和国广告法",
        article="第二十八条",
        excerpt="广告以虚假或者引人误解的内容欺骗、误导消费者的，构成虚假广告。",
        retrieval_text="广告 虚假广告 虚假宣传 引人误解 误导消费者 医疗功效 夸大宣传 商品宣传",
        reason_template="向量检索显示该工单与虚假宣传、医疗功效暗示或广告误导语义接近。",
    ),
    LegalArticle(
        source_id="anti_unfair_competition_law_8",
        law_name="中华人民共和国反不正当竞争法",
        article="第八条",
        excerpt="经营者不得对商品性能、功能、质量、销售状况、用户评价等作虚假或者引人误解的商业宣传。",
        retrieval_text="反不正当竞争 商业宣传 商品性能 商品功能 商品质量 虚假宣传 引人误解 功效 宣传",
        reason_template="向量检索显示该工单与商品功能、质量或功效方面的商业宣传争议语义接近。",
    ),
    LegalArticle(
        source_id="food_safety_law_148",
        law_name="中华人民共和国食品安全法",
        article="第一百四十八条",
        excerpt="消费者因不符合食品安全标准的食品受到损害的，可以依法要求赔偿；符合条件时可主张惩罚性赔偿。",
        retrieval_text="食品安全 食品 过期食品 保质期 标签 配料表 十倍赔偿 惩罚性赔偿 不符合食品安全标准",
        reason_template="向量检索显示该工单与食品安全、标签、保质期或惩罚性赔偿语义接近。",
    ),
    LegalArticle(
        source_id="product_quality_law_40",
        law_name="中华人民共和国产品质量法",
        article="第四十条",
        excerpt="售出的产品不具备应当具备的使用性能、存在质量问题的，销售者应当依法承担修理、更换、退货等责任。",
        retrieval_text="产品质量 商品质量 不合格 故障 使用性能 修理 更换 退货 退款 电器",
        reason_template="向量检索显示该工单与商品质量、退换货或产品不合格争议语义接近。",
    ),
    LegalArticle(
        source_id="medical_device_regulation",
        law_name="医疗器械监督管理条例",
        article="相关条款",
        excerpt="医疗器械注册、备案、标签说明书和宣传使用应当符合法规要求，不得作虚假或误导性表达。",
        retrieval_text="医疗器械 医疗功效 文号 企业执行标准 备案 注册 标签说明书 宣传 误导",
        reason_template="向量检索显示该工单与医疗器械属性、文号或医疗功效宣传语义接近。",
    ),
    LegalArticle(
        source_id="complaint_report_measure",
        law_name="市场监督管理投诉举报处理暂行办法",
        article="第九条至第十五条",
        excerpt="市场监督管理部门依法处理投诉举报，并按职责权限、管辖范围和材料完整性进行受理或分送。",
        retrieval_text="市场监督管理 投诉 举报 受理 管辖 分送 查处 职责范围 材料完整",
        reason_template="向量检索显示该工单与投诉举报受理、管辖或分送办理语义接近。",
    ),
    LegalArticle(
        source_id="price_fraud_rule",
        law_name="明码标价和禁止价格欺诈规定",
        article="相关条款",
        excerpt="经营者销售商品、提供服务应当明码标价，不得实施价格欺诈。",
        retrieval_text="价格 收费 乱收费 明码标价 价格欺诈 服务收费 停车费 价格争议",
        reason_template="向量检索显示该工单与价格、收费或价格欺诈争议语义接近。",
    ),
)

_VECTOR_INDEX: list[LegalVectorEntry] | None = None
_VECTOR_INDEX_MODEL = ""


def get_legal_retrieval_config_status() -> dict[str, object]:
    """返回法律条款混合检索配置，便于在接口中排查阈值和 Top K。"""

    return {
        "vector_top_k": LEGAL_VECTOR_TOP_K,
        "display_top_k": LEGAL_DISPLAY_TOP_K,
        "min_relevance_score": LEGAL_MIN_RELEVANCE_SCORE,
        "enable_reranker": LEGAL_ENABLE_RERANKER,
        "prewarm_on_startup": LEGAL_PREWARM_ON_STARTUP,
    }


def prewarm_legal_vector_index() -> dict[str, object]:
    """服务启动时预热法律知识库向量索引，避免首个工单承担建库耗时。"""

    if not LEGAL_PREWARM_ON_STARTUP:
        return {"enabled": False, "message": "LEGAL_PREWARM_ON_STARTUP=false，跳过预热。"}
    warmup_vector = embed_texts(["法律知识库向量索引预热"])[0]
    model = get_embedding_runtime_model()
    index = _get_vector_index(model)
    return {
        "enabled": True,
        "embedding_model": model,
        "warmup_dimension": len(warmup_vector),
        "article_count": len(index),
    }


def retrieve_legal_references(ticket: Ticket, structured: StructuredTicket, limit: int | None = None) -> list[LegalReference]:
    """对法律知识库执行向量召回、reranker 重排和阈值过滤。"""

    query_text = (
        f"{ticket.title}\n{ticket.content}\n{ticket.ticket_type}\n{ticket.appeal_purpose}\n"
        f"{structured.case_nature.value}\n{structured.appeal}\n{' '.join(structured.keywords)}"
    )
    query_vector = embed_texts([query_text])[0]
    query_model = get_embedding_runtime_model()
    scored = [
        (entry, cosine_similarity(query_vector, entry.vector))
        for entry in _get_vector_index(query_model)
    ]
    vector_candidates = [
        LegalCandidate(entry=entry, vector_score=score, final_score=score)
        for entry, score in sorted(scored, key=lambda item: item[1], reverse=True)[:LEGAL_VECTOR_TOP_K]
        if score > 0
    ]
    candidates = _rerank_candidates(query_text, vector_candidates)
    references = []
    display_limit = limit or LEGAL_DISPLAY_TOP_K
    for candidate in sorted(candidates, key=lambda item: item.final_score, reverse=True):
        if candidate.final_score < LEGAL_MIN_RELEVANCE_SCORE:
            continue
        entry = candidate.entry
        references.append(
            LegalReference(
                law_name=entry.article.law_name,
                article=entry.article.article,
                excerpt=entry.article.excerpt,
                relevance_score=round(candidate.final_score, 2),
                reason=_build_reference_reason(entry.article, candidate),
                retrieval_method="hybrid_vector_rerank" if candidate.rerank_score > 0 else "vector",
                embedding_model=entry.embedding_model,
                reranker_model=candidate.reranker_model,
                vector_score=round(candidate.vector_score, 2),
                rerank_score=round(candidate.rerank_score, 2),
                source_id=entry.article.source_id,
            )
        )
        if len(references) >= display_limit:
            break
    return references


def _rerank_candidates(query_text: str, candidates: list[LegalCandidate]) -> list[LegalCandidate]:
    """使用 reranker 对向量召回候选法条重排；未配置或失败时保留向量排序。"""

    if not LEGAL_ENABLE_RERANKER or not candidates:
        return candidates
    documents = [_article_to_rerank_text(candidate.entry.article) for candidate in candidates]
    reranked = rerank_documents(query_text, documents, top_n=min(len(candidates), LEGAL_DISPLAY_TOP_K))
    if not reranked:
        return candidates

    candidate_by_index = {index: candidate for index, candidate in enumerate(candidates)}
    updated = []
    for item in reranked:
        candidate = candidate_by_index.get(item.index)
        if candidate is None:
            continue
        updated.append(
            LegalCandidate(
                entry=candidate.entry,
                vector_score=candidate.vector_score,
                final_score=item.score,
                rerank_score=item.score,
                reranker_model=get_reranker_runtime_model(),
            )
        )
    return updated or candidates


def _get_vector_index(expected_model: str) -> list[LegalVectorEntry]:
    """构建并缓存 mock 法律知识库向量索引；模型变化时自动重建。"""

    global _VECTOR_INDEX, _VECTOR_INDEX_MODEL
    if _VECTOR_INDEX is None or _VECTOR_INDEX_MODEL != expected_model:
        vectors = embed_texts([_article_to_embedding_text(article) for article in LEGAL_KNOWLEDGE_BASE])
        index_model = get_embedding_runtime_model()
        _VECTOR_INDEX = [
            LegalVectorEntry(article=article, vector=vector, embedding_model=index_model)
            for article, vector in zip(LEGAL_KNOWLEDGE_BASE, vectors)
        ]
        _VECTOR_INDEX_MODEL = index_model
    return _VECTOR_INDEX


def _article_to_embedding_text(article: LegalArticle) -> str:
    """把法条元数据合并成用于入库的 embedding 文本。"""

    return f"{article.law_name}\n{article.article}\n{article.excerpt}\n{article.retrieval_text}"


def _article_to_rerank_text(article: LegalArticle) -> str:
    """把法条整理为 reranker 可比较的候选文本。"""

    return f"{article.law_name} {article.article}\n{article.excerpt}\n{article.retrieval_text}"


def _build_reference_reason(article: LegalArticle, candidate: LegalCandidate) -> str:
    """生成工作人员可读的法条推荐原因。"""

    if candidate.rerank_score > 0:
        return f"{article.reason_template}已经过 reranker 重排确认。"
    return article.reason_template
