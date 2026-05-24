from __future__ import annotations

from pathlib import Path
import re
from typing import Dict, List

def _brief_text(text: str, max_len: int = 80) -> str:
    t = (text or "").strip().replace("\n", " ")
    if len(t) <= max_len:
        return t
    return t[:max_len] + "..."


TEXT_CITATION_SUFFIXES = {
    ".txt",
    ".md",
    ".markdown",
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".html",
    ".css",
    ".csv",
    ".yml",
    ".yaml",
    ".toml",
    ".xml",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".go",
    ".rs",
    ".sql",
    ".sh",
    ".ps1",
}
CODE_CITATION_SUFFIXES = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".json",
    ".html",
    ".css",
    ".yml",
    ".yaml",
    ".toml",
    ".xml",
    ".java",
    ".c",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".go",
    ".rs",
    ".sql",
    ".sh",
    ".ps1",
}


def _decode_reference_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "utf-16", "utf-16-le", "utf-16-be"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _line_range_for_chunk(source_path: str, chunk_content: str) -> tuple[int | None, int | None]:
    if not source_path or not chunk_content:
        return None, None
    path = Path(source_path)
    if not path.exists() or not path.is_file():
        return None, None
    try:
        full_text = _decode_reference_text(path.read_bytes()).replace("\r\n", "\n").replace("\r", "\n")
    except OSError:
        return None, None

    needle = str(chunk_content or "").strip().replace("\r\n", "\n").replace("\r", "\n")
    if not needle:
        return None, None
    idx = full_text.find(needle)
    if idx < 0:
        return None, None

    start_line = full_text[:idx].count("\n") + 1
    end_line = start_line + max(needle.count("\n"), 0)
    return start_line, end_line


def _citation_kind(source_path: str, page_no: object) -> str:
    suffix = Path(source_path or "").suffix.lower()
    if suffix in {".ppt", ".pptx"}:
        return "slide"
    if suffix == ".pdf":
        return "pdf"
    if suffix in CODE_CITATION_SUFFIXES:
        return "code"
    if suffix in TEXT_CITATION_SUFFIXES:
        return "text"
    if page_no is not None:
        return "document"
    return "file"


def build_reference_items(chunks: List[Dict[str, object]], max_items: int = 8) -> List[Dict[str, object]]:
    refs: List[Dict[str, object]] = []
    for i, c in enumerate(chunks[:max_items], start=1):
        score_val = c.get("score")
        source_path = str(c.get("source_path", "") or "")
        suffix = Path(source_path).suffix.lower()
        kind = _citation_kind(source_path, c.get("page_no"))
        line_start = line_end = None
        if suffix in TEXT_CITATION_SUFFIXES:
            line_start, line_end = _line_range_for_chunk(source_path, str(c.get("content", "") or ""))
        page_no = c.get("page_no")
        document_id = c.get("document_id")
        target = {
            "kind": kind,
            "document_id": int(document_id) if isinstance(document_id, int) else document_id,
            "path": source_path or None,
            "source_path": source_path or None,
            "page_no": page_no,
            "line_start": line_start,
            "line_end": line_end,
            "chunk_id": c.get("chunk_id"),
        }
        refs.append(
            {
                "ref_id": f"ref-{i}",
                "citation_id": f"ref-{i}",
                "type": kind,
                "page_no": page_no,
                "line_start": line_start,
                "line_end": line_end,
                "summary": _brief_text(c.get("content", ""), max_len=100),
                "doucument_title": c.get("document_title", "未知文档"),
                "score": float(score_val) if isinstance(score_val, (int, float)) else None,
                "source_path": source_path or None,
                "document_id": document_id,
                "target": target,
            }
        )
    return refs


def build_inline_context_reference_items(
    user_text: str,
    *,
    start_index: int = 1,
    max_items: int = 8,
) -> List[Dict[str, object]]:
    refs: List[Dict[str, object]] = []
    seen: set[str] = set()

    selection_pattern = re.compile(
        r"<selection\s+[^>]*path=\"([^\"]*)\"[^>]*lines=\"([0-9]+)(?:-([0-9]+))?\"[^>]*>",
        re.IGNORECASE,
    )
    file_pattern = re.compile(r"<file\s+[^>]*path=\"([^\"]+)\"[^>]*>", re.IGNORECASE)

    def add_ref(kind: str, path_text: str, line_start: int | None = None, line_end: int | None = None) -> None:
        if len(refs) >= max_items:
            return
        source_path = str(path_text or "").strip()
        if not source_path:
            return
        key = f"{source_path}:{line_start}:{line_end}"
        if key in seen:
            return
        seen.add(key)
        suffix = Path(source_path).suffix.lower()
        target_kind = "code" if suffix in CODE_CITATION_SUFFIXES else kind
        idx = start_index + len(refs)
        refs.append(
            {
                "ref_id": f"ref-{idx}",
                "citation_id": f"ref-{idx}",
                "type": target_kind,
                "page_no": None,
                "line_start": line_start,
                "line_end": line_end,
                "summary": "用户本轮附加的上下文",
                "doucument_title": Path(source_path).name or source_path,
                "score": None,
                "source_path": source_path,
                "document_id": None,
                "target": {
                    "kind": target_kind,
                    "path": source_path,
                    "source_path": source_path,
                    "page_no": None,
                    "line_start": line_start,
                    "line_end": line_end,
                    "document_id": None,
                    "chunk_id": None,
                },
            }
        )

    for match in selection_pattern.finditer(user_text or ""):
        try:
            line_start = int(match.group(2))
            line_end = int(match.group(3) or line_start)
        except ValueError:
            line_start = line_end = None
        add_ref("text", match.group(1), line_start, line_end)

    for match in file_pattern.finditer(user_text or ""):
        add_ref("file", match.group(1))

    return refs


def build_retrieval_context(chunks: List[Dict[str, object]]) -> str:
    if not chunks:
        return ""
    lines = [
        "以下是可参考的资料片段，请优先依据这些内容回答；",
        "如果资料不足，请明确说“资料中未找到”。",
        "",
    ]
    for i, c in enumerate(chunks, start=1):
        title = str(c.get("document_title", "未知文档"))
        source_path = str(c.get("source_path", "") or "").strip()
        page_no = c.get("page_no")
        page_text = f"第{page_no}页" if page_no is not None else "未知页码"
        content = str(c.get("content", "")).strip()
        score = c.get("score")
        score_text = f"{float(score):.4f}" if isinstance(score, (int, float)) else "N/A"

        lines.append(f"[参考{i}] 来源：{title} | {page_text} | 相似度：{score_text}")
        if source_path:
            lines.append(f"路径：{source_path}")
        lines.append(content)
        lines.append("")
    return "\n".join(lines).strip()


def build_web_context(results: List[Dict[str, object]]) -> str:
    if not results:
        return ""
    lines = ["銆愯仈缃戞悳绱㈢粨鏋溿€戜互涓嬩负瀹炴椂鎼滅储鍒扮殑鍙傝€冧俊鎭細", ""]
    for i, r in enumerate(results, 1):
        lines.append(f"[缃戠粶{i}] {r.get('title', '')}")
        lines.append(f"来源：{r.get('url', '')}")
        lines.append(r.get("snippet", "").strip())
        lines.append("")
    return "\n".join(lines).strip()


def build_web_reference_items(
    results: List[Dict[str, object]],
    *,
    start_index: int = 1,
    max_items: int = 5,
) -> List[Dict[str, object]]:
    refs: List[Dict[str, object]] = []
    for result in results[:max_items]:
        idx = start_index + len(refs)
        url = str(result.get("url", "") or "").strip()
        title = str(result.get("title", "") or "").strip() or url or "web"
        refs.append(
            {
                "ref_id": f"ref-{idx}",
                "citation_id": f"ref-{idx}",
                "type": "web",
                "page_no": None,
                "line_start": None,
                "line_end": None,
                "summary": _brief_text(str(result.get("snippet", "") or ""), max_len=100),
                "doucument_title": title,
                "score": None,
                "source_path": url or None,
                "document_id": None,
                "target": {
                    "kind": "web",
                    "url": url,
                    "source_path": url or None,
                    "page_no": None,
                    "line_start": None,
                    "line_end": None,
                    "document_id": None,
                    "chunk_id": None,
                },
            }
        )
    return refs
