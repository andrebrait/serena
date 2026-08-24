"""TEMPORARY diagnostic (not for merge): measure Phpactor's initial workspace indexing.

Answers, per platform: does Phpactor report indexing progress, when does it report the end, and
what is in the index by then. Always fails so that pytest prints the collected payload.
"""

import json
import platform
import time
from pathlib import Path

import pytest

from solidlsp.language_servers.phpactor import PhpactorServer
from solidlsp.ls_config import LanguageServerId
from test.conftest import get_repo_path, start_ls_context

pytestmark = pytest.mark.php


def _describe_dir(path: Path) -> dict:
    if not path.exists():
        return {"path": str(path), "exists": False}
    entries = list(path.rglob("*"))
    return {
        "path": str(path),
        "exists": True,
        "files": sum(1 for e in entries if e.is_file()),
        "dirs": sum(1 for e in entries if e.is_dir()),
        "top_level": sorted(e.name for e in path.iterdir())[:20],
    }


def test_diag_phpactor_indexing_timeline() -> None:
    timeline: list[dict] = []
    original_on_progress = PhpactorServer._on_progress
    t0 = time.monotonic()

    def traced(self: PhpactorServer, params: dict) -> None:
        value = params.get("value") or {}
        timeline.append(
            {
                "t": round(time.monotonic() - t0, 2),
                "kind": value.get("kind"),
                "text": str(value.get("title") or value.get("message") or "")[:160],
            }
        )
        original_on_progress(self, params)

    PhpactorServer._on_progress = traced  # type: ignore[method-assign]
    payload: dict = {"platform": platform.platform(), "python": platform.python_version()}
    try:
        with start_ls_context(
            LanguageServerId.PHP_PHPACTOR,
            ls_specific_settings={
                LanguageServerId.PHP_PHPACTOR: {"file_filter": [".module"], "indexing_timeout": 600.0, "indexing_start_grace": 30.0}
            },
        ) as ls:
            t_query = time.monotonic()
            references = ls.request_references(str(get_repo_path(LanguageServerId.PHP_PHPACTOR) / "helper.php"), 2, len("function "))
            payload["query_seconds"] = round(time.monotonic() - t_query, 1)
            payload["references"] = [ref["uri"].split("/")[-1] for ref in references]
            payload["serena_cache"] = [_describe_dir(p) for p in sorted(Path(ls.cache_dir).glob("phpactor-index-*"))]
            payload["default_cache"] = _describe_dir(Path.home() / ".cache" / "phpactor")
    except Exception as e:  # noqa: BLE001 - diagnostic
        payload["exception"] = f"{type(e).__name__}: {str(e)[:400]}"
    finally:
        PhpactorServer._on_progress = original_on_progress  # type: ignore[method-assign]

    payload["timeline"] = timeline
    raise AssertionError("PHPACTOR_DIAG " + json.dumps(payload, indent=1))
