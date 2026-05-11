from dataclasses import dataclass
from importlib.util import find_spec
from shutil import which
from typing import Dict, List, Optional


@dataclass(frozen=True)
class ToolDependency:
    import_name: str
    package_name: str
    required: bool = True


@dataclass(frozen=True)
class ToolPlugin:
    plugin_id: str
    name: str
    category: str
    description: str
    dependencies: tuple[ToolDependency, ...]
    optional_commands: tuple[str, ...] = ()


TOOL_PLUGINS: tuple[ToolPlugin, ...] = (
    ToolPlugin(
        plugin_id="documents",
        name="Documents",
        category="document",
        description="Read PDF/TXT and work with DOCX documents.",
        dependencies=(
            ToolDependency("pypdf", "pypdf"),
            ToolDependency("docx", "python-docx"),
        ),
    ),
    ToolPlugin(
        plugin_id="spreadsheets",
        name="Spreadsheets",
        category="spreadsheet",
        description="Read, write, and analyze XLSX/CSV spreadsheet files.",
        dependencies=(
            ToolDependency("openpyxl", "openpyxl"),
            ToolDependency("pandas", "pandas"),
            ToolDependency("xlsxwriter", "XlsxWriter"),
        ),
    ),
    ToolPlugin(
        plugin_id="browser",
        name="Browser",
        category="browser",
        description="Automate browser sessions for page inspection and UI checks.",
        dependencies=(
            ToolDependency("playwright", "playwright"),
        ),
    ),
    ToolPlugin(
        plugin_id="github",
        name="GitHub",
        category="github",
        description="Access GitHub APIs and local Git repositories.",
        dependencies=(
            ToolDependency("github", "PyGithub"),
            ToolDependency("git", "GitPython"),
        ),
        optional_commands=("git", "gh"),
    ),
)


def get_tool_plugins() -> List[ToolPlugin]:
    return list(TOOL_PLUGINS)


def _dependency_status(dep: ToolDependency) -> Dict[str, object]:
    installed = find_spec(dep.import_name) is not None
    return {
        "import_name": dep.import_name,
        "package_name": dep.package_name,
        "required": dep.required,
        "installed": installed,
    }


def get_tool_plugin_status(plugin_id: Optional[str] = None) -> List[Dict[str, object]]:
    plugins = [
        plugin
        for plugin in TOOL_PLUGINS
        if plugin_id is None or plugin.plugin_id == plugin_id
    ]
    status: List[Dict[str, object]] = []
    for plugin in plugins:
        dependencies = [_dependency_status(dep) for dep in plugin.dependencies]
        required_ok = all(
            bool(dep["installed"])
            for dep in dependencies
            if bool(dep["required"])
        )
        status.append(
            {
                "plugin_id": plugin.plugin_id,
                "name": plugin.name,
                "category": plugin.category,
                "description": plugin.description,
                "installed": required_ok,
                "dependencies": dependencies,
                "optional_commands": {
                    command: which(command) is not None
                    for command in plugin.optional_commands
                },
            }
        )
    return status


def summarize_tool_plugin_status() -> Dict[str, bool]:
    return {
        str(item["plugin_id"]): bool(item["installed"])
        for item in get_tool_plugin_status()
    }
