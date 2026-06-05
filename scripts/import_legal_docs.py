from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from app.legal_pg_kb import import_legal_docx_directory  # noqa: E402


def main() -> None:
    """命令行导入法规 docx 到 PostgreSQL + pgvector 知识库。"""

    parser = argparse.ArgumentParser(description="导入市场监管法律法规 docx 到真实知识库")
    parser.add_argument("--path", default="legalDocx", help="法规 docx 目录，默认 legalDocx")
    parser.add_argument("--rebuild", action="store_true", help="导入前清空原有法规知识库")
    args = parser.parse_args()

    directory = Path(args.path)
    if not directory.is_absolute():
        directory = PROJECT_ROOT / directory
    result = import_legal_docx_directory(directory, rebuild=args.rebuild)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
