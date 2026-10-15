from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "input"
OUTPUT = ROOT / "data" / "DATA_MANIFEST.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    files = []
    for path in sorted(p for p in DATA_ROOT.rglob("*") if p.is_file()):
        files.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    payload = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "scope": "minimum cleaned reproducibility bundle for the private team repository",
        "file_count": len(files),
        "total_bytes": sum(item["bytes"] for item in files),
        "files": files,
    }
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT} with {len(files)} files")


if __name__ == "__main__":
    main()
