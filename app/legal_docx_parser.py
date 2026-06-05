from __future__ import annotations

import hashlib
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile


ARTICLE_PATTERN = re.compile(r"^第[一二三四五六七八九十百千万零〇两]+条")
CHAPTER_PATTERN = re.compile(r"^第[一二三四五六七八九十百千万零〇两]+章")


@dataclass(frozen=True)
class ParsedLegalChunk:
    """从法规文档中切分出的单个条文片段。"""

    chunk_key: str
    law_name: str
    chapter: str
    article: str
    chunk_text: str
    source_file: str
    sequence: int


@dataclass(frozen=True)
class ParsedLegalDocument:
    """法规文档解析结果，包含文档元数据和条文切片。"""

    document_key: str
    law_name: str
    revision_note: str
    source_file: str
    chunks: list[ParsedLegalChunk]


def parse_legal_docx(path: Path) -> ParsedLegalDocument:
    """解析 docx 法规文件，并按“第几条”切分为可向量化的知识库片段。"""

    paragraphs = _read_docx_paragraphs(path)
    if not paragraphs:
        raise ValueError(f"法规文档为空：{path}")

    law_name = paragraphs[0].strip()
    revision_note = paragraphs[1].strip() if len(paragraphs) > 1 and paragraphs[1].startswith("（") else ""
    document_key = _stable_key(str(path.resolve()), law_name)
    chunks = _split_articles(paragraphs, law_name, str(path))
    if not chunks:
        chunks = _split_paragraph_chunks(paragraphs, law_name, str(path))
    return ParsedLegalDocument(
        document_key=document_key,
        law_name=law_name,
        revision_note=revision_note,
        source_file=str(path),
        chunks=chunks,
    )


def parse_legal_docx_directory(directory: Path) -> list[ParsedLegalDocument]:
    """批量解析目录下所有 docx 法规文件。"""

    return [parse_legal_docx(path) for path in sorted(directory.rglob("*.docx"))]


def _read_docx_paragraphs(path: Path) -> list[str]:
    """从 docx 压缩包中的 document.xml 读取纯文本段落。"""

    with ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        text = "".join(node.text or "" for node in paragraph.findall(".//w:t", namespace)).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def _split_articles(paragraphs: list[str], law_name: str, source_file: str) -> list[ParsedLegalChunk]:
    """把法规正文按条文聚合，条文下的款项会并入同一个 chunk。"""

    chunks: list[ParsedLegalChunk] = []
    chapter = ""
    current_article = ""
    current_lines: list[str] = []

    def flush() -> None:
        if not current_article or not current_lines:
            return
        sequence = len(chunks) + 1
        chunk_text = "\n".join(current_lines).strip()
        chunks.append(
            ParsedLegalChunk(
                chunk_key=_stable_key(source_file, current_article, chunk_text),
                law_name=law_name,
                chapter=chapter,
                article=current_article,
                chunk_text=chunk_text,
                source_file=source_file,
                sequence=sequence,
            )
        )

    for text in _skip_catalog(paragraphs):
        if CHAPTER_PATTERN.match(text):
            flush()
            chapter = text
            current_article = ""
            current_lines = []
            continue
        if ARTICLE_PATTERN.match(text):
            flush()
            current_article = ARTICLE_PATTERN.match(text).group(0)
            current_lines = [text]
            continue
        if current_article:
            current_lines.append(text)

    flush()
    return chunks


def _skip_catalog(paragraphs: list[str]) -> list[str]:
    """跳过目录区，避免目录中的章节标题被误认为正文。"""

    if "目　　录" not in paragraphs and "目录" not in paragraphs:
        return paragraphs

    catalog_index = next(
        index for index, text in enumerate(paragraphs) if text in {"目　　录", "目录"}
    )
    for index in range(catalog_index + 1, len(paragraphs)):
        if CHAPTER_PATTERN.match(paragraphs[index]):
            next_chapter = paragraphs[index]
            for body_index in range(index + 1, len(paragraphs)):
                if paragraphs[body_index] == next_chapter:
                    return paragraphs[:catalog_index] + paragraphs[body_index:]
            return paragraphs[:catalog_index] + paragraphs[index:]
    return paragraphs


def _split_paragraph_chunks(
    paragraphs: list[str],
    law_name: str,
    source_file: str,
    max_chars: int = 900,
) -> list[ParsedLegalChunk]:
    """没有“第几条”结构时按段落合并分片，兼容决定、公告类法规文件。"""

    body_paragraphs = []
    for text in _skip_catalog(paragraphs):
        if text == law_name or text.startswith("（"):
            continue
        if CHAPTER_PATTERN.match(text):
            continue
        body_paragraphs.append(text)

    chunks: list[ParsedLegalChunk] = []
    current_lines: list[str] = []
    current_length = 0
    for text in body_paragraphs:
        if current_lines and current_length + len(text) > max_chars:
            _append_paragraph_chunk(chunks, current_lines, law_name, source_file)
            current_lines = []
            current_length = 0
        current_lines.append(text)
        current_length += len(text)
    if current_lines:
        _append_paragraph_chunk(chunks, current_lines, law_name, source_file)
    return chunks


def _append_paragraph_chunk(
    chunks: list[ParsedLegalChunk],
    lines: list[str],
    law_name: str,
    source_file: str,
) -> None:
    """追加一个按段落兜底生成的法规片段。"""

    sequence = len(chunks) + 1
    article = f"全文片段{sequence}"
    chunk_text = "\n".join(lines).strip()
    chunks.append(
        ParsedLegalChunk(
            chunk_key=_stable_key(source_file, article, chunk_text),
            law_name=law_name,
            chapter="",
            article=article,
            chunk_text=chunk_text,
            source_file=source_file,
            sequence=sequence,
        )
    )


def _stable_key(*parts: str) -> str:
    """生成稳定主键，便于重复导入时更新同一文档或条文。"""

    digest = hashlib.sha256("||".join(parts).encode("utf-8")).hexdigest()
    return digest[:32]
