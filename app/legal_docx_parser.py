from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
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


SUPPORTED_LEGAL_EXTENSIONS = {".docx", ".doc", ".pdf"}


def parse_legal_document(path: Path) -> ParsedLegalDocument:
    """解析 docx、doc 或文本型 pdf 法规文件，并切分为知识库片段。"""

    suffix = path.suffix.lower()
    if suffix == ".docx":
        paragraphs = _read_docx_paragraphs(path)
    elif suffix == ".doc":
        paragraphs = _read_doc_paragraphs(path)
    elif suffix == ".pdf":
        paragraphs = _read_pdf_paragraphs(path)
    else:
        raise ValueError(f"不支持的法规文件类型：{path.suffix}")
    return _build_parsed_document(path, paragraphs)


def parse_legal_docx(path: Path) -> ParsedLegalDocument:
    """兼容旧调用：解析 docx 法规文件，并按“第几条”切分。"""

    return _build_parsed_document(path, _read_docx_paragraphs(path))


def _build_parsed_document(path: Path, paragraphs: list[str]) -> ParsedLegalDocument:
    """把已经提取出的段落整理成统一的法规文档解析结果。"""

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
    """批量解析目录下所有 docx、doc 和文本型 pdf 法规文件。"""

    documents = []
    for path in sorted(directory.rglob("*")):
        if path.is_file() and path.suffix.lower() in SUPPORTED_LEGAL_EXTENSIONS:
            documents.append(parse_legal_document(path))
    return documents


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


def _read_doc_paragraphs(path: Path) -> list[str]:
    """把旧版 doc 转换为临时 docx 后读取段落。"""

    soffice = _find_libreoffice()
    with tempfile.TemporaryDirectory(prefix="legal_doc_convert_") as temp_dir:
        temp_path = Path(temp_dir)
        command = [
            soffice,
            "--headless",
            "--convert-to",
            "docx",
            "--outdir",
            str(temp_path),
            str(path),
        ]
        result = subprocess.run(command, capture_output=True, text=True, timeout=120)
        if result.returncode != 0:
            message = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(f"doc 转 docx 失败：{path}；{message}")
        converted_files = list(temp_path.glob("*.docx"))
        if not converted_files:
            raise RuntimeError(f"doc 转 docx 后未生成文件：{path}")
        return _read_docx_paragraphs(converted_files[0])


def _read_pdf_paragraphs(path: Path) -> list[str]:
    """读取文本型 PDF 段落；不处理扫描图片 PDF。"""

    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("缺少 pypdf 依赖，请先安装 requirements.txt。") from exc

    logging.getLogger("pypdf").setLevel(logging.ERROR)
    reader = PdfReader(str(path))
    paragraphs = []
    for page in reader.pages:
        text = page.extract_text() or ""
        for line in text.splitlines():
            normalized = line.strip()
            if normalized:
                paragraphs.append(normalized)
    if not paragraphs:
        raise ValueError(f"PDF 未提取到文本内容：{path}")
    return paragraphs


def _find_libreoffice() -> str:
    """查找 LibreOffice/soffice 可执行文件，用于旧版 doc 转换。"""

    candidates = [
        os.getenv("LIBREOFFICE_PATH", ""),
        shutil.which("soffice") or "",
        shutil.which("libreoffice") or "",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
    ]
    for candidate in candidates:
        if not candidate:
            continue
        if Path(candidate).exists() or shutil.which(candidate):
            return candidate
    raise RuntimeError("未找到 LibreOffice，请安装 LibreOffice 或配置 LIBREOFFICE_PATH。")


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
