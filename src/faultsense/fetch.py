"""Download the manuals listed in the manifest and verify their checksums."""
from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path
from typing import Callable

from faultsense.manifest import ManualSpec

# Schneider's download server answers 403 to non-browser user agents.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36"
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, dest: Path) -> None:
    request = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/pdf,*/*"}
    )
    partial = dest.with_name(dest.name + ".part")
    with urllib.request.urlopen(request, timeout=120) as response, open(partial, "wb") as out:
        while chunk := response.read(1 << 20):
            out.write(chunk)
    partial.replace(dest)


def fetch_manuals(
    specs: list[ManualSpec],
    manuals_dir: Path,
    downloader: Callable[[str, Path], None] = download,
) -> list[tuple[str, str]]:
    manuals_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for spec in specs:
        dest = spec.path(manuals_dir)
        if dest.exists() and sha256_file(dest) == spec.sha256:
            results.append((spec.id, "present"))
            continue
        downloader(spec.url, dest)
        ok = sha256_file(dest) == spec.sha256
        results.append((spec.id, "downloaded" if ok else "checksum-mismatch"))
    return results
