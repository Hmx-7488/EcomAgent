"""Fail when repository candidates contain secrets, artifacts or platform SDKs.

Only Git tracked files and unignored untracked candidates are inspected. A local
``backend/.env`` is explicitly excluded and is never opened.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath


REPO_ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_SIZE = 2 * 1024 * 1024

FORBIDDEN_PATH_PARTS = {
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "uploads",
    "dist",
    "playwright-report",
    "test-results",
}
FORBIDDEN_EXACT_PATHS = {
    "backend/.env",
    "docs/prototype.zip",
}
DATABASE_SUFFIXES = {".db", ".sqlite", ".sqlite3"}

SECRET_PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "google_api_key": re.compile(rb"\bAIza[0-9A-Za-z_-]{30,}\b"),
    "aws_access_key": re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
    "provider_bearer_key": re.compile(rb"\bsk-[0-9A-Za-z_-]{24,}\b"),
}

SOURCE_SUFFIXES = {
    ".py",
    ".pyi",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".vue",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
}
PLATFORM_SDK_PATTERNS = {
    "taobao": re.compile(
        r"(?im)(?:from|import|require\s*\()\s*[\"']?(?:taobao|top[_-]?api|open[_-]?taobao)"
    ),
    "pinduoduo": re.compile(
        r"(?im)(?:from|import|require\s*\()\s*[\"']?(?:pinduoduo|pdd[_-]?open)"
    ),
    "douyin": re.compile(
        r"(?im)(?:from|import|require\s*\()\s*[\"']?(?:douyin|jinritemai|oceanengine)"
    ),
    "xiaohongshu": re.compile(
        r"(?im)(?:from|import|require\s*\()\s*[\"']?(?:xiaohongshu|xhs[_-]?open)"
    ),
}


def _git_candidates() -> list[str]:
    command = [
        "git",
        "-C",
        str(REPO_ROOT),
        "ls-files",
        "--cached",
        "--others",
        "--exclude-standard",
        "-z",
    ]
    output = subprocess.run(command, check=True, capture_output=True).stdout
    return sorted(
        path.decode("utf-8", errors="surrogateescape")
        for path in output.split(b"\0")
        if path
    )


def main() -> int:
    findings: list[dict[str, str]] = []
    scanned = 0
    candidates = _git_candidates()
    for relative in candidates:
        normalized = relative.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if normalized in FORBIDDEN_EXACT_PATHS:
            findings.append({"type": "forbidden_path", "path": normalized})
            continue
        if pure.name == ".env" or (
            pure.name.startswith(".env.") and pure.name != ".env.example"
        ):
            findings.append({"type": "environment_secret_file", "path": normalized})
            continue
        if any(part in FORBIDDEN_PATH_PARTS for part in pure.parts):
            findings.append({"type": "generated_or_runtime_path", "path": normalized})
            continue
        if pure.suffix.lower() in DATABASE_SUFFIXES:
            findings.append({"type": "database_artifact", "path": normalized})
            continue

        absolute = REPO_ROOT / Path(*pure.parts)
        if not absolute.is_file() or absolute.stat().st_size > MAX_TEXT_SIZE:
            continue
        payload = absolute.read_bytes()
        scanned += 1
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(payload):
                findings.append({"type": name, "path": normalized})
        if pure.suffix.lower() in SOURCE_SUFFIXES:
            text = payload.decode("utf-8", errors="ignore")
            for platform, pattern in PLATFORM_SDK_PATTERNS.items():
                if pattern.search(text):
                    findings.append(
                        {"type": f"platform_sdk:{platform}", "path": normalized}
                    )

    report = {
        "candidate_files": len(candidates),
        "scanned_text_files": scanned,
        "findings": findings,
        "passed": not findings,
        "note": "backend/.env is excluded by path and was never opened",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if not findings else 1


if __name__ == "__main__":
    raise SystemExit(main())
