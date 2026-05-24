from __future__ import annotations

from datetime import datetime
from html import escape
from pathlib import Path

LOG_HTML_PATH = Path("logs/error_logs.html")
LOG_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)


def ensure_log_html_exists() -> None:
    if LOG_HTML_PATH.exists():
        return
    LOG_HTML_PATH.write_text(
        """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8" />
<title>Error Log</title>
<style>
body { font-family: Arial, sans-serif; margin: 24px; }
table { border-collapse: collapse; width: 100%; }
th, td { border: 1px solid #ddd; padding: 8px; text-align: left; vertical-align: top; }
th { background: #f5f5f5; }
tr:nth-child(even) { background: #fafafa; }
</style>
</head>
<body>
<h2>AI Assistant Error Log</h2>
<table>
<thead>
<tr>
<th>时间</th>
<th>会话ID</th>
<th>耗时(ms)</th>
<th>错误类型</th>
<th>错误详情</th>
</tr>
</thead>
<tbody>
</tbody>
</table>
</body>
</html>
""",
        encoding="utf-8",
    )


def append_error_row(session_id: str, latency_ms: int, error_type: str, detail: str) -> None:
    ensure_log_html_exists()
    html_text = LOG_HTML_PATH.read_text(encoding="utf-8")

    row = (
        "<tr>"
        f"<td>{escape(datetime.now().strftime('%Y-%m-%d %H:%M:%S'))}</td>"
        f"<td>{escape(session_id)}</td>"
        f"<td>{latency_ms}</td>"
        f"<td>{escape(error_type)}</td>"
        f"<td>{escape(detail)}</td>"
        "</tr>"
    )

    marker = "</tbody>"
    if marker in html_text:
        html_text = html_text.replace(marker, row + marker, 1)
        LOG_HTML_PATH.write_text(html_text, encoding="utf-8")
