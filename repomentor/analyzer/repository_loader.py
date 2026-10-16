"""Load a project from a ZIP upload or a public GitHub URL into a temp folder.

Security notes:
* ZIP entries are validated before extraction (path traversal / "ZIP Slip",
  absolute paths, symlinks, entry count and total uncompressed size).
* GitHub repositories are downloaded as a single archive (one HTTP request),
  which avoids the 60 requests/hour unauthenticated API limit that a
  file-by-file contents walk would quickly hit.
* Nothing is ever imported or executed from the uploaded project.
"""

from __future__ import annotations

import io
import os
import re
import shutil
import stat
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterator

import requests

from repomentor.utils.constants import (
    MAX_ARCHIVE_BYTES,
    MAX_ARCHIVE_ENTRIES,
    MAX_UNCOMPRESSED_BYTES,
)

GITHUB_URL = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]{0,38}))/"
    r"(?P<repo>[A-Za-z0-9._-]+?)(?:\.git)?(?:/(?:tree|blob)/(?P<ref>[^/?#]+)(?:/(?P<subpath>[^?#]*))?)?/?(?:[?#].*)?$"
)
USER_AGENT = "RepoMentor-AI/1.0 (+https://github.com)"


class LoaderError(Exception):
    """Raised with a user-facing (Turkish) message when loading fails."""


@dataclass
class GitHubRef:
    owner: str
    repo: str
    ref: str | None = None
    subpath: str | None = None

    @property
    def url(self) -> str:
        return f"https://github.com/{self.owner}/{self.repo}"


@dataclass
class LoadedProject:
    root: Path
    name: str
    source: str
    source_url: str | None = None
    github: dict | None = None


def parse_github_url(url: str) -> GitHubRef:
    match = GITHUB_URL.match(url.strip())
    if not match:
        raise LoaderError(
            "Geçerli bir GitHub adresi değil. Örnek: https://github.com/kullanici/proje"
        )
    subpath = (match.group("subpath") or "").strip("/") or None
    return GitHubRef(match.group("owner"), match.group("repo"), match.group("ref"), subpath)


# --- ZIP handling ---------------------------------------------------------------

def _is_symlink(info: zipfile.ZipInfo) -> bool:
    return stat.S_ISLNK(info.external_attr >> 16)


MB = 1024 * 1024


def _check_limits(data: bytes, entries: list[zipfile.ZipInfo]) -> None:
    if len(data) > MAX_ARCHIVE_BYTES:
        raise LoaderError(f"Arşiv çok büyük (sınır: {MAX_ARCHIVE_BYTES // MB} MB).")
    if len(entries) > MAX_ARCHIVE_ENTRIES:
        raise LoaderError(f"Arşivde çok fazla dosya var (sınır: {MAX_ARCHIVE_ENTRIES}).")
    if sum(info.file_size for info in entries) > MAX_UNCOMPRESSED_BYTES:
        raise LoaderError(f"Arşivin açılmış boyutu çok büyük (sınır: {MAX_UNCOMPRESSED_BYTES // MB} MB).")


def _safe_target(root: Path, info: zipfile.ZipInfo) -> Path:
    """Resolve where an entry would land; refuse anything outside `root` (ZIP Slip)."""
    name = info.filename.replace("\\", "/")
    pure = PurePosixPath(name)
    target = (root / pure).resolve()
    escapes = pure.is_absolute() or ".." in pure.parts or re.match(r"^[A-Za-z]:", name)
    if escapes or (root != target and root not in target.parents):
        raise LoaderError(f"Güvensiz dosya yolu reddedildi: {name!r} (ZIP Slip koruması)")
    return target


def _copy_capped(archive: zipfile.ZipFile, info: zipfile.ZipInfo, target: Path) -> None:
    """Copy with a hard cap: the size in the header can lie."""
    target.parent.mkdir(parents=True, exist_ok=True)
    with archive.open(info) as src, open(target, "wb") as dst:
        remaining = info.file_size + 1
        while chunk := src.read(min(1 << 16, remaining)):
            remaining -= len(chunk)
            if remaining <= 0:
                raise LoaderError("Arşiv başlığı ile içerik boyutu uyuşmuyor; işlem durduruldu.")
            dst.write(chunk)


def safe_extract_zip(data: bytes, destination: Path) -> None:
    """Extract an archive while refusing anything that could escape `destination`."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        if len(data) > MAX_ARCHIVE_BYTES:
            raise LoaderError(f"Arşiv çok büyük (sınır: {MAX_ARCHIVE_BYTES // MB} MB).") from exc
        raise LoaderError("Dosya geçerli bir ZIP arşivi değil veya bozuk.") from exc
    with archive:
        entries = archive.infolist()
        _check_limits(data, entries)
        root = destination.resolve()
        for info in entries:
            target = _safe_target(root, info)
            if _is_symlink(info):
                continue  # symlinks could point outside the sandbox; skip them
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                _copy_capped(archive, info, target)


def project_root(extracted: Path) -> Path:
    """GitHub and most zip tools wrap everything in one top-level folder; unwrap it."""
    children = [p for p in extracted.iterdir() if p.name not in {"__MACOSX", ".DS_Store"}]
    if len(children) == 1 and children[0].is_dir():
        return children[0]
    return extracted


# --- GitHub ---------------------------------------------------------------------

def _github_headers() -> dict[str, str]:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def fetch_github_metadata(ref: GitHubRef, timeout: float = 10) -> dict | None:
    """Best effort: repository description, stars, licence, default branch.

    Returns None on rate limits or network errors; the download path does
    not depend on it.
    """
    try:
        resp = requests.get(
            f"https://api.github.com/repos/{ref.owner}/{ref.repo}",
            headers=_github_headers(),
            timeout=timeout,
        )
    except requests.RequestException:
        return None
    if resp.status_code == 404:
        raise LoaderError("Depo bulunamadı. Adresin doğru ve deponun herkese açık (public) olduğundan emin olun.")
    if resp.status_code != 200:
        return None
    data = resp.json()
    if data.get("private"):
        raise LoaderError("Bu sürüm yalnızca herkese açık (public) depoları destekler.")
    return {
        "full_name": data.get("full_name"),
        "description": data.get("description"),
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "open_issues": data.get("open_issues_count", 0),
        "default_branch": data.get("default_branch"),
        "license": (data.get("license") or {}).get("spdx_id"),
        "topics": data.get("topics", []),
        "language": data.get("language"),
        "pushed_at": data.get("pushed_at"),
        "homepage": data.get("homepage"),
    }


def download_github_archive(ref: GitHubRef, branch: str | None, timeout: float = 30) -> bytes:
    archive_ref = branch or "HEAD"
    url = f"https://codeload.github.com/{ref.owner}/{ref.repo}/zip/{archive_ref}"
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout, stream=True)
    except requests.RequestException as exc:
        raise LoaderError(f"GitHub'a bağlanılamadı: {exc.__class__.__name__}") from exc
    with resp:
        if resp.status_code == 404:
            raise LoaderError("Depo veya dal (branch) bulunamadı ya da depo herkese açık değil.")
        if resp.status_code != 200:
            raise LoaderError(f"GitHub arşivi indirilemedi (HTTP {resp.status_code}).")
        buffer = io.BytesIO()
        try:
            for chunk in resp.iter_content(chunk_size=1 << 16):
                buffer.write(chunk)
                if buffer.tell() > MAX_ARCHIVE_BYTES:
                    raise LoaderError(
                        f"Depo çok büyük (sınır: {MAX_ARCHIVE_BYTES // (1024 * 1024)} MB)."
                    )
        except requests.RequestException as exc:
            raise LoaderError("GitHub indirmesi kesildi. Bağlantınızı kontrol edip yeniden deneyin.") from exc
        return buffer.getvalue()


# --- Public API -------------------------------------------------------------------

@contextmanager
def _workspace() -> Iterator[Path]:
    """Temporary folder that is always deleted, even if analysis fails."""
    path = Path(tempfile.mkdtemp(prefix="repomentor_"))
    try:
        yield path
    finally:
        shutil.rmtree(path, ignore_errors=True)


@contextmanager
def load_zip(data: bytes, filename: str = "project.zip") -> Iterator[LoadedProject]:
    with _workspace() as work:
        extract_dir = work / "project"
        extract_dir.mkdir()
        safe_extract_zip(data, extract_dir)
        root = project_root(extract_dir)
        name = Path(filename).stem if root == extract_dir else root.name
        yield LoadedProject(root=root, name=name, source="zip")


@contextmanager
def load_github(url: str) -> Iterator[LoadedProject]:
    ref = parse_github_url(url)
    metadata = fetch_github_metadata(ref)
    branch = ref.ref or (metadata or {}).get("default_branch")
    data = download_github_archive(ref, branch)
    with _workspace() as work:
        extract_dir = work / "project"
        extract_dir.mkdir()
        safe_extract_zip(data, extract_dir)
        root = project_root(extract_dir)
        if ref.subpath:
            candidate = (root / ref.subpath).resolve()
            if not candidate.is_dir() or root.resolve() not in candidate.parents:
                raise LoaderError(f"Alt klasör bulunamadı: {ref.subpath}")
            root = candidate
        name = ref.repo if not ref.subpath else f"{ref.repo}/{ref.subpath}"
        source_url = ref.url
        if ref.ref:
            source_url += f"/tree/{ref.ref}"
            if ref.subpath:
                source_url += f"/{ref.subpath}"
        yield LoadedProject(root=root, name=name, source="github", source_url=source_url, github=metadata)


@contextmanager
def load_local(path: str | Path, source: str = "local") -> Iterator[LoadedProject]:
    """Analyse a folder in place (CLI and bundled demo projects). Read-only."""
    root = Path(path).resolve()
    if not root.is_dir():
        raise LoaderError(f"Klasör bulunamadı: {path}")
    yield LoadedProject(root=root, name=root.name, source=source)
