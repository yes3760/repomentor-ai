"""High-entropy strings that look like credentials even when nothing names them as one.

A random 40-character token stored as `client = Client("Xb9…")` passes every
name-based rule. Shannon entropy (bits per character) separates random tokens
from words and identifiers: English text sits around 3.5–4.0 bits, random
base64 near 6, random hex near 4. Thresholds follow common secret scanners:
hex ≥ 3.0 over ≥ 32 characters, other token alphabets ≥ 4.3 over ≥ 20.

False positives are kept down by the value's *context* (the variable, keyword
or key it is assigned to): hashes, versions, colours, patterns, ids, paths and
the like are skipped, and so are UUIDs, regex-like strings and test files.
"""

from __future__ import annotations

import ast
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import PurePosixPath

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.taint.sources import call_name
from repomentor.utils.text_utils import mask_value

HEX = re.compile(r"^[0-9a-fA-F]+$")
TOKEN_CHARS = re.compile(r"^[A-Za-z0-9+/=_\-.]+$")
UUID = re.compile(r"^[0-9a-f]{8}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{4}-?[0-9a-f]{12}$", re.I)
SAFE_CONTEXT = re.compile(
    r"hash|sha\d*|md5|checksum|digest|uuid|guid|(^|_)ids?$|version|colou?r|regex|pattern|path|url|uri|dir|file|name|label|title|"
    r"query|template|format|css|html|style|icon|image|img|font|locale|encoding|mime|type|kind|mode|algorithm|integrity|"
    r"etag|commit|revision|example|sample|placeholder|fixture|selector|xpath|slug|sku|isbn|barcode",
    re.I,
)
CONFIG_SUFFIXES = {".json", ".yml", ".yaml", ".toml", ".ini", ".cfg"}
CONFIG_LINE = re.compile(r"""^\s*["']?([\w.-]+)["']?\s*[:=]\s*["']?([A-Za-z0-9+/=_\-.]{20,})["']?\s*,?\s*$""")
HEX_LIMIT, TOKEN_LIMIT = 3.0, 4.3


@dataclass
class EntropyHit:
    file: str
    line: int
    context: str
    value: str
    entropy: float


def shannon(value: str) -> float:
    counts = Counter(value)
    return -sum(n / len(value) * math.log2(n / len(value)) for n in counts.values())


def _token_shaped(value: str) -> bool:
    """Right length and alphabet, letters and digits both present, not a UUID."""
    if not 20 <= len(value) <= 256 or not TOKEN_CHARS.match(value) or UUID.match(value):
        return False
    return any(c.isdigit() for c in value) and any(c.isalpha() for c in value)


def looks_random(value: str) -> bool:
    if not _token_shaped(value):
        return False
    if HEX.match(value):
        return len(value) >= 32 and shannon(value) >= HEX_LIMIT
    mixed_case = value.lower() != value != value.upper()
    # Random tokens scatter digits (~15 % of base64); identifiers like `LongClassName2` carry one or two.
    digits = sum(c.isdigit() for c in value)
    return mixed_case and digits >= max(3, len(value) // 12) and shannon(value) >= TOKEN_LIMIT


def _suspicious(context: str, value: str) -> bool:
    """Overlap with the name-based rule is removed later by line (`skip`), not here: that rule only
    sees quoted values, so an unquoted YAML `credential: …` must still be caught by entropy."""
    return not SAFE_CONTEXT.search(context) and looks_random(value)


def _dict_items(node: ast.Dict) -> list[tuple[str, ast.expr]]:
    return [(k.value, v) for k, v in zip(node.keys, node.values, strict=False) if isinstance(k, ast.Constant) and isinstance(k.value, str)]


def _named_values(node: ast.AST) -> list[tuple[str, ast.expr]]:
    """(context, value) pairs one node gives a name to: assignment target, keyword, dict key, called function."""
    if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
        return [(ast.unparse(t), node.value) for t in getattr(node, "targets", [getattr(node, "target", None)])]
    if isinstance(node, ast.keyword):
        return [(node.arg, node.value)] if node.arg else []
    if isinstance(node, ast.Dict):
        return _dict_items(node)
    return [(call_name(node.func), a) for a in node.args] if isinstance(node, ast.Call) else []


def _python_candidates(tree: ast.Module) -> list[tuple[str, ast.Constant]]:
    """(context, string constant) pairs where a context name is known."""
    return [(context, value) for node in ast.walk(tree) for context, value in _named_values(node)
            if isinstance(value, ast.Constant) and isinstance(value.value, str)]


def _hits_in_python(path: str, tree: ast.Module) -> list[EntropyHit]:
    return [
        EntropyHit(path, constant.lineno, context, constant.value, round(shannon(constant.value), 2))
        for context, constant in _python_candidates(tree) if _suspicious(context, constant.value)
    ]


def _hits_in_config(path: str, text: str) -> list[EntropyHit]:
    hits = []
    for number, line in enumerate(text.splitlines(), 1):
        if (match := CONFIG_LINE.match(line)) and _suspicious(match.group(1), match.group(2)):
            hits.append(EntropyHit(path, number, match.group(1), match.group(2), round(shannon(match.group(2)), 2)))
    return hits


def find_high_entropy(project: ProjectFiles, skip: set[tuple[str, int]]) -> list[EntropyHit]:
    """Random-looking values outside tests; `skip` holds lines another secret rule already reported."""
    hits: list[EntropyHit] = []
    python = set(project.python_files)
    for path, text in project.texts.items():
        name = PurePosixPath(path).name.lower()
        if project.is_test(path) or any(marker in name for marker in ("example", "sample", "template", "lock")):
            continue
        if path in python and (tree := project.tree(path)) is not None:
            hits += _hits_in_python(path, tree)
        elif PurePosixPath(path).suffix in CONFIG_SUFFIXES:
            hits += _hits_in_config(path, text)
    return [h for h in hits if (h.file, h.line) not in skip]


def describe_hit(hit: EntropyHit) -> str:
    entropy = f"{hit.entropy:.1f}".replace(".", ",")
    return f'`{hit.context} = "{mask_value(hit.value)}"` ({len(hit.value)} karakter, entropi {entropy} bit)'
