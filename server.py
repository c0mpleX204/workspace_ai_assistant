"""Backward-compatible backend entrypoint.

Use `server/main.py` as the canonical backend layout going forward.
"""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


def _load_app_from_new_layout():
    main_path = Path(__file__).parent / "server" / "main.py"
    spec = spec_from_file_location("workspace_backend_main", main_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Failed to load backend entry: {main_path}")
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.app


app = _load_app_from_new_layout()


if __name__ == "__main__":
    import uvicorn

    from server.config.config import settings

    uvicorn.run(app, host=settings.host, port=settings.port, reload=False)

