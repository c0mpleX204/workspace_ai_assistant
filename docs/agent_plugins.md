# Agent Plugin Capabilities

This project keeps Codex-like agent capabilities as Python runtime packages plus a small registry in `server/agent_core/tool_registry.py`.

## Installed capability groups

- `documents`: `pypdf` for PDF text extraction and `python-docx` for DOCX files.
- `spreadsheets`: `openpyxl`, `pandas`, and `XlsxWriter` for XLSX/CSV reading, analysis, and writing.
- `browser`: `playwright` for browser automation and UI checks.
- `github`: `PyGithub` for GitHub API access and `GitPython` for local repository operations.

## Verify locally

```powershell
@'
from server.agent_core.tool_registry import get_tool_plugin_status
for item in get_tool_plugin_status():
    print(item["plugin_id"], item["installed"])
'@ | .\.venv\Scripts\python.exe -
```

For the browser capability, install browser binaries after installing packages:

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
```
