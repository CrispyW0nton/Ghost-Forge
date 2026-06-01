from __future__ import annotations

from pathlib import Path


def test_storage_owns_data_root_path_literals():
    core_root = Path(__file__).resolve().parents[1]
    offenders: list[str] = []
    for path in core_root.rglob("*.py"):
        if path.name == "storage.py" or path.parts[-2] == "tests":
            continue
        text = path.read_text(encoding="utf-8")
        if '"data/' in text or "'data/" in text or "os.path.join" in text:
            offenders.append(str(path.relative_to(core_root)))

    assert offenders == []
