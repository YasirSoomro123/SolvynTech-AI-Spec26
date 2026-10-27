"""Session-state helpers for the UI, kept free of Streamlit so they can be unit-tested.

The bug these exist for: a chat opened for part A must never be shown, or sent to the model,
while part B is being answered.  So every conversation is keyed by the folder it was read
from *and* the part it is about, and the analysis cache is keyed by the files themselves -
not by the part number alone, which would serve a stale report after the folder changed.
"""

from __future__ import annotations

import hashlib
import os
from collections.abc import MutableMapping
from pathlib import Path

CHAT_KEY = "chat_history"

READABLE = {".xlsx", ".xlsm", ".xls", ".csv", ".pdf", ".igs", ".iges", ".txt"}


def history_key(folder: str | os.PathLike[str], part: str) -> str:
    """Stable key for one conversation: this folder, this part, nothing else."""
    raw = f"{Path(str(folder)).as_posix().lower()}|{str(part).strip().lower()}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def file_stamp(folder: str | os.PathLike[str]) -> str:
    """Fingerprint of the files in `folder` (recursively): name, size, modified-time.

    Used as part of the analysis cache key so that replacing, editing or adding a file
    invalidates the cached report, while an untouched folder keeps it.
    """
    root = Path(folder)
    if not root.is_dir():
        return "missing"
    entries = []
    for path in sorted(root.rglob("*"), key=lambda p: p.as_posix().lower()):
        if not path.is_file() or path.name.startswith(("~$", ".")):
            continue
        if path.suffix.lower() not in READABLE:
            continue
        try:
            stat = path.stat()
        except OSError:
            continue
        entries.append(f"{path.relative_to(root).as_posix().lower()}:{stat.st_size}"
                       f":{stat.st_mtime_ns}")
    digest = hashlib.sha1("\n".join(entries).encode("utf-8")).hexdigest()[:16]
    return f"{len(entries)}-{digest}"


def get_history(state: MutableMapping, key: str) -> list[dict]:
    """The conversation for `key`, created empty the first time it is asked for."""
    store = state.setdefault(CHAT_KEY, {})
    return store.setdefault(key, [])


def append_turn(state: MutableMapping, key: str, question: str, answer: dict) -> None:
    get_history(state, key).append({"role": "user", "text": question})
    get_history(state, key).append({"role": "assistant", **answer})


def clear_history(state: MutableMapping, key: str) -> None:
    state.setdefault(CHAT_KEY, {})[key] = []
