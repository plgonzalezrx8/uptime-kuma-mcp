"""Fail CI on high-confidence secrets in repository and release artifacts."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import tarfile
import zipfile
from collections.abc import Iterable
from pathlib import Path

_PATTERNS = {
    "private key": re.compile(b"-----BEGIN " + rb"(?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{36,}\b"),
    "AWS access key": re.compile(rb"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "Slack token": re.compile(rb"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
    "Stripe live key": re.compile(rb"\b[rs]k_live_[A-Za-z0-9]{16,}\b"),
}
_FORBIDDEN_ARTIFACT_NAMES = {".env", ".coverage"}


def _repository_files() -> list[Path]:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required for repository secret scanning")
    result = subprocess.run(  # noqa: S603 - executable is resolved from the trusted CI PATH
        [git, "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    )
    return [Path(item.decode()) for item in result.stdout.split(b"\0") if item]


def _matches(label: str, data: bytes) -> Iterable[str]:
    for name, pattern in _PATTERNS.items():
        if pattern.search(data):
            yield f"{label}: {name}"


def _scan_archive(path: Path) -> Iterable[str]:
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive:
            for zip_member in archive.infolist():
                member_path = Path(zip_member.filename)
                if member_path.name in _FORBIDDEN_ARTIFACT_NAMES:
                    yield f"{path}:{zip_member.filename}: forbidden artifact file"
                if not zip_member.is_dir():
                    yield from _matches(f"{path}:{zip_member.filename}", archive.read(zip_member))
        return
    if tarfile.is_tarfile(path):
        with tarfile.open(path) as archive:
            for tar_member in archive.getmembers():
                member_path = Path(tar_member.name)
                if member_path.name in _FORBIDDEN_ARTIFACT_NAMES:
                    yield f"{path}:{tar_member.name}: forbidden artifact file"
                if tar_member.isfile():
                    extracted = archive.extractfile(tar_member)
                    if extracted is not None:
                        yield from _matches(f"{path}:{tar_member.name}", extracted.read())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path)
    args = parser.parse_args()

    findings: list[str] = []
    for path in _repository_files():
        if path.is_file():
            findings.extend(_matches(str(path), path.read_bytes()))
    if args.artifacts and args.artifacts.exists():
        for path in args.artifacts.iterdir():
            if path.is_file():
                findings.extend(_scan_archive(path))

    if findings:
        print("High-confidence secret scan failed:")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("High-confidence secret scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
