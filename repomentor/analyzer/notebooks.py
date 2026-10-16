"""Jupyter notebooks as analysable Python.

The code cells of a notebook share one namespace and run top to bottom, so a
scaler fitted in cell 6 and a `train_test_split` in cell 7 are one leak. The
cells are therefore joined, in order, into one virtual script that every
analyzer reads like a `.py` file. Each cell starts with a `# %% [hücre N]`
marker line (N counts every cell, markdown included, as the reader sees them).

IPython syntax is neutralised without moving any line: `%magic` and `!shell`
lines become `pass`, `files = !ls` becomes `files = None`, and cells whose cell
magic switches language (`%%bash`, `%%sql`, …) or that do not parse are left
empty and listed as skipped. Outputs are never read.

`relocate` runs once on the finished result and turns every virtual line back
into "hücre N, satır M", in locations and in finding texts alike.
"""

from __future__ import annotations

import ast
import json
import re
from bisect import bisect_right
from dataclasses import dataclass, field, fields, is_dataclass

# Cell magics whose body is still Python; any other `%%name` switches language.
PYTHON_CELL_MAGICS = {"time", "timeit", "capture", "prun", "debug", "memit", "autoreload", "pdb"}
MAGIC_ASSIGNMENT = re.compile(r"^(\s*)([\w\s,]+?)\s*=\s*[!%]")
HELP_LINE = re.compile(r"^[\w.]+\?{1,2}$")


@dataclass
class NotebookMap:
    """Where each cell starts in the virtual script."""

    starts: list[int] = field(default_factory=list)    # marker line of each code cell (1-based)
    cells: list[int] = field(default_factory=list)     # its position in the notebook (1-based, all cell types)
    skipped: list[int] = field(default_factory=list)   # code cells left out: another language or a syntax error

    def locate(self, line: int) -> tuple[int, int]:
        """(cell, line inside the cell) for a line of the virtual script."""
        index = bisect_right(self.starts, line) - 1
        if index < 0:
            return (self.cells[0] if self.cells else 1), line
        return self.cells[index], max(line - self.starts[index], 1)

    def label(self, path: str, line: int) -> str:
        cell, local = self.locate(line)
        return f"{path} › hücre {cell}:{local}"


def _is_python(notebook: dict) -> bool:
    metadata = notebook.get("metadata") or {}
    language = (metadata.get("kernelspec") or {}).get("language") or (metadata.get("language_info") or {}).get("name")
    return not language or str(language).lower() in {"python", "python3", "ipython", "ipython3"}


def _cells(notebook: dict) -> list[dict]:
    """nbformat 4 keeps cells at the top; nbformat 3 inside worksheets."""
    if isinstance(notebook.get("cells"), list):
        return notebook["cells"]
    return [cell for sheet in notebook.get("worksheets") or [] for cell in sheet.get("cells") or []]


def _source(cell: dict) -> str:
    source = cell.get("source", cell.get("input", ""))
    return "".join(source) if isinstance(source, list) else str(source or "")


def _python_line(line: str) -> str:
    stripped = line.lstrip()
    indent = line[: len(line) - len(stripped)]
    if match := MAGIC_ASSIGNMENT.match(line):
        return f"{match.group(1)}{match.group(2).strip()} = None"      # files = !ls
    if stripped.startswith(("%", "!")) or HELP_LINE.match(stripped):
        return f"{indent}pass"                                           # %matplotlib inline, !pip install, df?
    return line


def cell_code(text: str) -> str | None:
    """The Python in one code cell, same number of lines; None for another language."""
    lines = text.splitlines()
    if lines and lines[0].lstrip().startswith("%%"):
        magic = lines[0].lstrip()[2:].split(maxsplit=1)
        if not magic or magic[0] not in PYTHON_CELL_MAGICS:
            return None
        lines[0] = ""
    return "\n".join(_python_line(line) for line in lines)


def _parses(code: str) -> bool:
    try:
        ast.parse(code)
    except (SyntaxError, ValueError):
        return False
    return True


def notebook_source(raw: str) -> tuple[str, NotebookMap] | None:
    """(virtual script, cell map) for a Python notebook; None for invalid JSON or another kernel language."""
    try:
        notebook = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(notebook, dict) or not _is_python(notebook):
        return None
    lines: list[str] = []
    mapping = NotebookMap()
    for number, cell in enumerate(_cells(notebook), 1):
        if not isinstance(cell, dict) or cell.get("cell_type") != "code":
            continue
        code = cell_code(_source(cell))
        if code is None or not _parses(code):
            mapping.skipped.append(number)
            code = ""
        mapping.starts.append(len(lines) + 1)
        mapping.cells.append(number)
        lines.append(f"# %% [hücre {number}]")
        lines.extend(code.splitlines())
    return "\n".join(lines) + "\n", mapping


# --- Mapping results back to cells ----------------------------------------------------------------------------

def _moved(obj: object, notebooks: dict[str, NotebookMap]) -> None:
    """`file`/`line` pairs (locations, findings, metrics) point at the cell; a taint source in another cell says so."""
    path, line = getattr(obj, "file", None), getattr(obj, "line", None)
    if not (isinstance(path, str) and path in notebooks and isinstance(line, int) and line > 0):
        return
    mapping = notebooks[path]
    cell, local = mapping.locate(line)
    obj.file, obj.line = f"{path} › hücre {cell}", local
    source_line = getattr(obj, "source_line", None)
    if isinstance(source_line, int) and source_line > 0:
        source_cell, obj.source_line = mapping.locate(source_line)
        if source_cell != cell:
            obj.source = f"{obj.source} (hücre {source_cell})"


class _Relocator:
    def __init__(self, notebooks: dict[str, NotebookMap]):
        self.notebooks = notebooks
        names = "|".join(re.escape(p) for p in sorted(notebooks, key=len, reverse=True))
        self.reference = re.compile(rf"({names}):(\d+)")
        self.seen: set[int] = set()

    def text(self, value: str) -> str:
        if not any(path in value for path in self.notebooks):
            return value
        return self.reference.sub(lambda m: self.notebooks[m.group(1)].label(m.group(1), int(m.group(2))), value)

    def walk(self, obj: object) -> None:
        if id(obj) in self.seen or isinstance(obj, (str, bytes, int, float, bool, type(None))):
            return
        self.seen.add(id(obj))
        if isinstance(obj, (list, tuple, set)):
            for item in obj:
                self.walk(item)
        elif isinstance(obj, dict):
            for item in obj.values():
                self.walk(item)
        elif is_dataclass(obj) and not isinstance(obj, type):
            self._dataclass(obj)

    def _dataclass(self, obj: object) -> None:
        for item in fields(obj):
            value = getattr(obj, item.name)
            if isinstance(value, str) and item.name != "file":
                setattr(obj, item.name, self.text(value))
            else:
                self.walk(value)
        _moved(obj, self.notebooks)


def relocate(result: object, notebooks: dict[str, NotebookMap]) -> None:
    """Rewrite every virtual-script line in `result` as a notebook cell and a line inside it, in place."""
    if notebooks:
        _Relocator(notebooks).walk(result)
