"""Walk a project folder, filter noise and load text files into memory."""

from __future__ import annotations

import ast
import fnmatch
import os
import re
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

from repomentor.models.analysis_result import FileInfo
from repomentor.utils.constants import (
    IGNORED_DIRS,
    IGNORED_SUFFIXES,
    LANGUAGE_BY_EXTENSION,
    LOCK_FILES,
    MAX_ANALYZED_FILES,
    MAX_FILE_SIZE,
    MAX_LOCK_FILE_SIZE,
    TEXT_EXTENSIONS,
    TEXT_FILENAMES,
)
from repomentor.utils.text_utils import decode_bytes


@dataclass
class ProjectFiles:
    """In-memory view of a project that every analyzer works from."""

    root: Path
    files: list[FileInfo]
    texts: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    syntax_errors: dict[str, str] = field(default_factory=dict)
    _trees: dict[str, ast.Module | None] = field(default_factory=dict, repr=False)

    @property
    def paths(self) -> list[str]:
        return [f.path for f in self.files]

    @property
    def python_files(self) -> list[str]:
        return [p for p in self.texts if p.endswith(".py")]

    @property
    def source_python_files(self) -> list[str]:
        return [p for p in self.python_files if not self.is_test(p)]

    @property
    def test_python_files(self) -> list[str]:
        return [p for p in self.python_files if self.is_test(p)]

    def is_test(self, path: str) -> bool:
        """Path rules first; a `test_*.py` name alone must also look like a test."""
        verdict = is_test_path(path)
        if verdict != "maybe":
            return verdict
        return bool(TEST_MARKERS.search(self.texts.get(path, "")))

    def by_name(self, *names: str) -> list[str]:
        """Paths whose basename matches one of `names` (case-insensitive), shallowest first."""
        wanted = {n.lower() for n in names}
        found = [f.path for f in self.files if PurePosixPath(f.path).name.lower() in wanted]
        return sorted(found, key=lambda p: (p.count("/"), p))

    def at_root(self, *names: str) -> list[str]:
        return [p for p in self.by_name(*names) if "/" not in p]

    def text(self, path: str) -> str | None:
        return self.texts.get(path)

    def tree(self, path: str) -> ast.Module | None:
        """Parsed AST for a Python file, cached; None if it does not parse."""
        if path not in self._trees:
            try:
                self._trees[path] = ast.parse(self.texts[path], filename=path)
            except (SyntaxError, ValueError) as exc:
                self._trees[path] = None
                self.syntax_errors[path] = f"{exc.__class__.__name__}: {getattr(exc, 'msg', exc)} (satır {getattr(exc, 'lineno', '?')})"
        return self._trees[path]

    def parsed_python(self, include_tests: bool = True) -> list[tuple[str, ast.Module]]:
        paths = self.python_files if include_tests else self.source_python_files
        return [(p, t) for p in paths if (t := self.tree(p)) is not None]


TEST_MARKERS = re.compile(r"^\s*(?:async\s+)?def test|^\s*class Test|^\s*(?:import|from) (?:pytest|unittest)\b", re.M)


def is_test_path(path: str) -> bool | str:
    """True / False from the path alone, or "maybe" for `test_*.py` names
    that need a content check (e.g. a module called `test_analyzer.py`)."""
    parts = PurePosixPath(path).parts
    name = parts[-1]
    if any(part in {"tests", "test", "testing"} for part in parts[:-1]) or name == "conftest.py":
        return True
    if name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py")):
        return "maybe"
    return False


def _is_ignored_dir(name: str) -> bool:
    return name in IGNORED_DIRS or name.endswith(IGNORED_SUFFIXES)


def _is_text_candidate(path: PurePosixPath) -> bool:
    return (
        path.suffix.lower() in TEXT_EXTENSIONS
        or path.name in TEXT_FILENAMES
        or path.name.lower().startswith(("readme", "license", "licence", "changelog", "contributing", "requirements", ".env"))
    )


def _read_priority(path: str) -> tuple[int, int, str]:
    """Python sources and project metadata first, everything else after."""
    p = PurePosixPath(path)
    if p.suffix == ".py":
        rank = 0
    elif p.name.lower().startswith(("readme", "requirements", "license", "pyproject", "setup", ".env")) or p.name in TEXT_FILENAMES:
        rank = 1
    elif p.suffix in {".toml", ".cfg", ".ini", ".yml", ".yaml", ".md"}:
        rank = 2
    else:
        rank = 3
    return (rank, path.count("/"), path)


IGNORE_FILE = ".repomentorignore"


def load_ignore_patterns(root: Path) -> list[str]:
    """Glob patterns from `.repomentorignore` (one per line, `#` comments, `dir/` for folders)."""
    path = root / IGNORE_FILE
    if not path.is_file():
        return []
    lines = (line.strip() for line in path.read_text(encoding="utf-8", errors="ignore").splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def is_user_ignored(rel: str, patterns: list[str]) -> bool:
    """True when `rel` matches a `.repomentorignore` pattern (folder prefix or glob)."""
    for pattern in patterns:
        if pattern.endswith("/") and (rel + "/").startswith(pattern.lstrip("/")):
            return True
        if fnmatch.fnmatch(rel, pattern.lstrip("/")) or fnmatch.fnmatch(PurePosixPath(rel).name, pattern):
            return True
    return False


@dataclass
class _Walk:
    files: list[FileInfo] = field(default_factory=list)
    candidates: list[tuple[str, Path]] = field(default_factory=list)   # text files to read
    user_ignored: int = 0


def _walk(root: Path, patterns: list[str]) -> _Walk:
    """List files, skipping noise folders, symlinks and user-ignored paths."""
    walk = _Walk()
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not _is_ignored_dir(d))
        for full in (Path(dirpath) / name for name in sorted(filenames) if name != ".DS_Store"):
            rel = full.relative_to(root).as_posix()
            if full.is_symlink():
                continue
            if patterns and is_user_ignored(rel, patterns):
                walk.user_ignored += 1
                continue
            _register(walk, rel, full)
    return walk


def _register(walk: _Walk, rel: str, full: Path) -> None:
    size = full.stat().st_size
    pure = PurePosixPath(rel)
    info = FileInfo(path=rel, size=size, language=LANGUAGE_BY_EXTENSION.get(pure.suffix.lower()))
    walk.files.append(info)
    if not _is_text_candidate(pure):
        return
    limit = MAX_LOCK_FILE_SIZE if pure.name in LOCK_FILES else MAX_FILE_SIZE
    if size > limit:
        info.skipped_reason = f"Dosya çok büyük ({size // 1024} KB)"
    else:
        walk.candidates.append((rel, full))


def _read_texts(project: ProjectFiles, candidates: list[tuple[str, Path]]) -> None:
    """Read the highest-priority text files into memory, up to MAX_ANALYZED_FILES."""
    by_path = {f.path: f for f in project.files}
    candidates = sorted(candidates, key=lambda c: _read_priority(c[0]))
    if len(candidates) > MAX_ANALYZED_FILES:
        project.warnings.append(
            f"Proje {len(candidates)} metin dosyası içeriyor; ilk {MAX_ANALYZED_FILES} dosya analiz edildi (öncelik Python kaynaklarında)."
        )
        for rel, _ in candidates[MAX_ANALYZED_FILES:]:
            by_path[rel].skipped_reason = "Dosya sınırı aşıldı"
    for rel, full in candidates[:MAX_ANALYZED_FILES]:
        text = decode_bytes(full.read_bytes())
        if text is None:
            by_path[rel].skipped_reason = "İkili (binary) dosya"
            continue
        project.texts[rel] = text
        by_path[rel].lines = len(text.splitlines())


def scan_project(root: Path) -> ProjectFiles:
    """Build the in-memory view of a project folder. Nothing is executed."""
    root = root.resolve()
    walk = _walk(root, load_ignore_patterns(root))
    project = ProjectFiles(root=root, files=walk.files)
    if walk.user_ignored:
        project.warnings.append(f"{walk.user_ignored} dosya projenin `{IGNORE_FILE}` dosyası nedeniyle analiz dışında bırakıldı.")
    _read_texts(project, walk.candidates)
    oversized = sum(1 for f in walk.files if f.skipped_reason and "büyük" in f.skipped_reason)
    if oversized:
        project.warnings.append(f"{oversized} dosya boyut sınırını ({MAX_FILE_SIZE // 1000} KB) aştığı için içeriği incelenmedi.")
    return project


def language_breakdown(project: ProjectFiles) -> dict[str, int]:
    """Lines of code per language, using only files that were read."""
    totals: dict[str, int] = {}
    for f in project.files:
        if f.language and f.lines:
            totals[f.language] = totals.get(f.language, 0) + f.lines
    return dict(sorted(totals.items(), key=lambda kv: -kv[1]))


def render_tree(paths: list[str], max_entries: int = 400) -> str:
    """ASCII tree for reports and the LLM prompt."""
    tree: dict = {}
    for path in paths[:max_entries]:
        node = tree
        for part in PurePosixPath(path).parts:
            node = node.setdefault(part, {})

    lines: list[str] = []

    def walk(node: dict, prefix: str) -> None:
        entries = sorted(node.items(), key=lambda kv: (not kv[1], kv[0].lower()))
        for index, (name, child) in enumerate(entries):
            last = index == len(entries) - 1
            lines.append(f"{prefix}{'└── ' if last else '├── '}{name}{'/' if child else ''}")
            if child:
                walk(child, prefix + ("    " if last else "│   "))

    walk(tree, "")
    if len(paths) > max_entries:
        lines.append(f"… ve {len(paths) - max_entries} dosya daha")
    return "\n".join(lines)
