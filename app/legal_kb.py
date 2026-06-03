from __future__ import annotations

from dataclasses import dataclass

from app.models import LegalReference, StructuredTicket, Ticket


@dataclass(frozen=True)
class LegalArticle:
    """mock 法律知识库条目，后续可替换为数据库、全文检索或向量库。"""

    law_name: str
    article: str
    excerpt: str
    keywords: tuple[str, ...]
    reason_template: str


LEGAL_KNOWLEDGE_BASE: tuple[LegalArticle, ...] = (
    LegalArticle(
        law_name="中华人民共和国消费者权益保护法",
        article="第五十五条",
        excerpt="经营者提供商品或者服务有欺诈行为的，消费者可以依法主张增加赔偿。",
        keywords=("赔偿", "欺诈", "虚假宣传", "退款", "退货", "消费纠纷", "消费者"),
        reason_template="工单涉及消费者权益、退款赔偿或欺诈争议。",
    ),
    LegalArticle(
        law_name="中华人民共和国广告法",
        article="第二十八条",
        excerpt="广告以虚假或者引人误解的内容欺骗、误导消费者的，构成虚假广告。",
        keywords=("广告", "虚假宣传", "医疗功效", "夸大宣传", "误导消费者", "宣传"),
        reason_template="工单内容涉及虚假宣传、医疗功效暗示或广告误导。",
    ),
    LegalArticle(
        law_name="中华人民共和国反不正当竞争法",
        article="第八条",
        excerpt="经营者不得对商品性能、功能、质量、销售状况、用户评价等作虚假或者引人误解的商业宣传。",
        keywords=("虚假宣传", "商业宣传", "误导", "质量", "功能", "功效"),
        reason_template="工单涉及商品功能、质量或功效方面的商业宣传争议。",
    ),
    LegalArticle(
        law_name="中华人民共和国食品安全法",
        article="第一百四十八条",
        excerpt="消费者因不符合食品安全标准的食品受到损害的，可以依法要求赔偿；符合条件时可主张惩罚性赔偿。",
        keywords=("食品", "过期食品", "十倍赔偿", "食品安全法", "标签", "配料表", "保质期"),
        reason_template="工单涉及食品安全、标签、保质期或惩罚性赔偿。",
    ),
    LegalArticle(
        law_name="中华人民共和国产品质量法",
        article="第四十条",
        excerpt="售出的产品不具备应当具备的使用性能、存在质量问题的，销售者应当依法承担修理、更换、退货等责任。",
        keywords=("质量", "产品质量", "退货", "退款", "不合格", "故障", "电器"),
        reason_template="工单涉及商品质量、退换货或产品不合格争议。",
    ),
    LegalArticle(
        law_name="医疗器械监督管理条例",
        article="相关条款",
        excerpt="医疗器械注册、备案、标签说明书和宣传使用应当符合法规要求，不得作虚假或误导性表达。",
        keywords=("医疗器械", "医疗功效", "文号", "企业执行标准", "备案", "注册"),
        reason_template="工单涉及医疗器械属性、文号或医疗功效宣传。",
    ),
    LegalArticle(
        law_name="市场监督管理投诉举报处理暂行办法",
        article="第九条至第十五条",
        excerpt="市场监督管理部门依法处理投诉举报，并按职责权限、管辖范围和材料完整性进行受理或分送。",
        keywords=("投诉", "举报", "受理", "管辖", "分送", "市场监管", "查处"),
        reason_template="工单涉及投诉举报受理、管辖或分送办理。",
    ),
    LegalArticle(
        law_name="明码标价和禁止价格欺诈规定",
        article="相关条款",
        excerpt="经营者销售商品、提供服务应当明码标价，不得实施价格欺诈。",
        keywords=("价格", "收费", "乱收费", "明码标价", "价格欺诈"),
        reason_template="工单涉及价格、收费或价格欺诈争议。",
    ),
)


def retrieve_legal_references(ticket: Ticket, structured: StructuredTicket, limit: int = 5) -> list[LegalReference]:
    """根据工单文本检索可能涉及的法律条款，当前使用 mock 关键词检索。"""

    text = f"{ticket.title} {ticket.content} {ticket.ticket_type} {ticket.appeal_purpose} {' '.join(structured.keywords)}"
    scored: list[LegalReference] = []
    for article in LEGAL_KNOWLEDGE_BASE:
        matched = [keyword for keyword in article.keywords if keyword and keyword in text]
        if not matched:
            continue
        score = min(1.0, 0.35 + 0.12 * len(matched))
        scored.append(
            LegalReference(
                law_name=article.law_name,
                article=article.article,
                excerpt=article.excerpt,
                matched_keywords=matched,
                relevance_score=round(score, 2),
                reason=article.reason_template,
            )
        )

    return sorted(scored, key=lambda item: item.relevance_score, reverse=True)[:limit]
