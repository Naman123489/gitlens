"""Safe repository acquisition.

Constraints enforced here, all of which matter because the content is untrusted:

* ``git clone`` runs with hooks disabled, credential helpers disabled, terminal
  prompts disabled and submodules skipped. Cloning never executes repository
  content, and disabling hooks removes the one path that could.
* The clone is depth-limited by default and hard-capped by wall-clock timeout.
* The on-disk size is checked before the walker is allowed to read the tree.
* Nothing is installed, built or run. Ever.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)

DEFAULT_CLONE_DEPTH = 500
DEFAULT_TIMEOUT = 300
DEFAULT_MAX_BYTES = 512 * 1024 * 1024

_GIT_SAFE_ARGS = [
    "-c", "core.hooksPath=/dev/null",
    "-c", "credential.helper=",
    "-c", "protocol.ext.allow=never",
    "-c", "protocol.file.allow=never",
    "-c", "http.followRedirects=false",
    "-c", "advice.detachedHead=false",
]


class FetchError(RuntimeError):
    pass


@dataclass(slots=True)
class FetchedRepository:
    path: Path
    clone_url: str
    default_branch: str | None
    head_sha: str | None
    size_bytes: int
    shallow: bool
    _temp_root: Path | None = None

    def cleanup(self) -> None:
        if self._temp_root and self._temp_root.exists():
            shutil.rmtree(self._temp_root, ignore_errors=True)

    def __enter__(self) -> "FetchedRepository":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.cleanup()


def _authenticated_url(clone_url: str, token: str | None) -> str:
    """Embed a token for private clones without logging it.

    The URL is passed to git via argv and never written to the console or to the
    database; callers must not log the return value.
    """
    if not token:
        return clone_url
    parsed = urlparse(clone_url)
    if parsed.scheme != "https":
        raise FetchError("only https clone URLs are supported")
    return f"https://x-access-token:{quote(token, safe='')}@{parsed.netloc}{parsed.path}"


def _directory_size(path: Path, cap: int) -> int:
    total = 0
    for root, dirs, files in os.walk(path):
        if ".git" in dirs and root == str(path):
            pass  # .git is counted: it is real disk usage
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
            if total > cap:
                return total
    return total


@dataclass(slots=True)
class RemoteProbe:
    """What can be learned about a repository from git alone, with no API call."""

    reachable: bool
    default_branch: str | None = None
    head_sha: str | None = None
    branches: list[str] = field(default_factory=list)
    error: str | None = None


def probe_public_repository(clone_url: str, timeout: int = 30) -> RemoteProbe:
    """Check that a repository is publicly readable, using ``git ls-remote``.

    This exists so a public repository can be imported when the GitHub REST API
    is unavailable — no OAuth app configured, an API outage, or a network policy
    that permits git but not api.github.com. The resulting record carries less
    metadata (no stars, topics or languages), and that is recorded on the
    repository rather than filled in with guesses.
    """
    if not clone_url.startswith("https://"):
        return RemoteProbe(reachable=False, error="only https clone URLs are supported")
    env = {
        "GIT_TERMINAL_PROMPT": "0", "GIT_ASKPASS": "/bin/true", "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": "/tmp", "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    for name in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy",
                 "no_proxy", "SSL_CERT_FILE", "GIT_SSL_CAINFO"):
        if name in os.environ:
            env[name] = os.environ[name]
    try:
        result = subprocess.run(
            ["git", *_GIT_SAFE_ARGS, "ls-remote", "--symref", clone_url, "HEAD"],
            capture_output=True, text=True, timeout=timeout, env=env, check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        return RemoteProbe(reachable=False, error=f"{type(exc).__name__}: {exc}"[:200])
    if result.returncode != 0:
        return RemoteProbe(reachable=False, error=result.stderr.strip()[:300] or "ls-remote failed")

    default_branch = None
    head_sha = None
    for line in result.stdout.splitlines():
        if line.startswith("ref:"):
            parts = line.split()
            if len(parts) >= 2:
                default_branch = parts[1].rsplit("/", 1)[-1]
        elif "\tHEAD" in line:
            head_sha = line.split("\t")[0].strip()
    return RemoteProbe(
        reachable=True, default_branch=default_branch or "main", head_sha=head_sha,
    )


def clone_repository(
    clone_url: str,
    token: str | None = None,
    branch: str | None = None,
    depth: int | None = DEFAULT_CLONE_DEPTH,
    timeout: int = DEFAULT_TIMEOUT,
    max_bytes: int = DEFAULT_MAX_BYTES,
    destination: Path | None = None,
) -> FetchedRepository:
    """Clone ``clone_url`` into a temporary directory.

    Raises :class:`FetchError` on timeout, on git failure, or when the clone
    exceeds ``max_bytes``. The partial clone is always removed on failure.
    """
    if not clone_url.startswith("https://"):
        raise FetchError("refusing to clone a non-https URL")

    temp_root = Path(destination) if destination else Path(tempfile.mkdtemp(prefix="repolens-"))
    target = temp_root / "repo"
    args = ["git", *_GIT_SAFE_ARGS, "clone", "--no-checkout" if False else "--quiet",
            "--no-tags", "--recurse-submodules=no"]
    if depth:
        args += ["--depth", str(depth)]
    if branch:
        args += ["--branch", branch, "--single-branch"]
    args += [_authenticated_url(clone_url, token), str(target)]

    env = {
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_ASKPASS": "/bin/true",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_ALLOW_PROTOCOL": "https",
        "HOME": str(temp_root),
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
    }
    for proxy_var in ("HTTPS_PROXY", "HTTP_PROXY", "NO_PROXY", "https_proxy", "http_proxy",
                      "no_proxy", "SSL_CERT_FILE", "GIT_SSL_CAINFO"):
        if proxy_var in os.environ:
            env[proxy_var] = os.environ[proxy_var]

    try:
        completed = subprocess.run(
            args, capture_output=True, text=True, timeout=timeout, env=env, check=False
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise FetchError(f"clone timed out after {timeout}s") from exc

    if completed.returncode != 0:
        shutil.rmtree(temp_root, ignore_errors=True)
        # Strip any credential that git may have echoed back in the error.
        message = _redact(completed.stderr.strip() or "git clone failed", token)
        raise FetchError(f"clone failed: {message[:400]}")

    size = _directory_size(target, max_bytes)
    if size > max_bytes:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise FetchError(
            f"repository is larger than the {max_bytes // (1024 * 1024)} MB analysis limit"
        )

    head_sha = _git_output(target, ["rev-parse", "HEAD"], env)
    head_branch = _git_output(target, ["rev-parse", "--abbrev-ref", "HEAD"], env)

    return FetchedRepository(
        path=target, clone_url=clone_url, default_branch=head_branch, head_sha=head_sha,
        size_bytes=size, shallow=bool(depth), _temp_root=temp_root,
    )


def _git_output(path: Path, args: list[str], env: dict[str, str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *_GIT_SAFE_ARGS, *args], cwd=path, capture_output=True, text=True,
            timeout=30, env=env, check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None


def _redact(message: str, token: str | None) -> str:
    if token:
        message = message.replace(token, "[REDACTED]").replace(quote(token, safe=""), "[REDACTED]")
    return message.replace("x-access-token:", "x-access-token:[REDACTED]@").split("@")[-1] \
        if "x-access-token" in message else message
