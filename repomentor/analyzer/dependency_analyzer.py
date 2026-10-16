"""Known vulnerabilities in pinned dependencies, looked up in the free OSV.dev database.

Only packages whose exact version is known are queried (`==` pins and lock
files); for `>=1.0` style ranges the installed version is unknowable, so they
are reported as "not checked" instead of guessed. Only package names and
versions leave the machine – never source code.
"""

from __future__ import annotations

import json
import re
import time
import tomllib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from math import floor
from pathlib import PurePosixPath

import requests
from packaging.version import InvalidVersion, Version

from repomentor.analyzer.file_tree import ProjectFiles
from repomentor.analyzer.rules import make_issue
from repomentor.models.analysis_result import DependencyReport, Vulnerability, VulnerablePackage
from repomentor.models.issue import SEVERITY_LABELS, SEVERITY_ORDER, Issue, Location

OSV_QUERY_URL = "https://api.osv.dev/v1/query"
OSV_PAGE_URL = "https://osv.dev/vulnerability/{id}"
MAX_PACKAGES = 150
WORKERS = 8
REQUEST_TIMEOUT = 10
CACHE_SECONDS = 6 * 3600
MAX_PAGES = 3

REQUIREMENT_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*(.*)$")
EXACT_PIN = re.compile(r"^===?\s*([A-Za-z0-9][A-Za-z0-9.+!_-]*)\s*$")
VULN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{2,80}$")
LOCAL_SOURCES = ("editable", "virtual", "directory", "path")


class OSVError(Exception):
    """User-facing (Turkish) error from the OSV lookup."""


@dataclass(frozen=True)
class PinnedDependency:
    name: str           # normalised (PEP 503)
    version: str
    file: str
    line: int | None = None


def normalise(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


# --- Collecting exact versions --------------------------------------------------------

def _is_requirements_file(path: str) -> bool:
    p = PurePosixPath(path)
    in_folder = p.parent.name == "requirements" and p.suffix == ".txt"
    return path.count("/") <= 2 and (in_folder or (p.name.startswith("requirements") and p.suffix in {".txt", ".in", ".lock"}))


def _requirement_lines(path: str, text: str) -> tuple[list[PinnedDependency], list[str]]:
    pinned, loose = [], []
    for lineno, raw in enumerate(text.splitlines(), 1):
        line = raw.split(" #", 1)[0].split(";", 1)[0].split("--hash", 1)[0].strip()
        if not line or line.startswith(("#", "-", "git+", "http://", "https://", ".", "/")):
            continue
        if not (match := REQUIREMENT_LINE.match(line)):
            continue
        name, spec = normalise(match.group(1)), match.group(3).strip().rstrip("\\").strip()
        if exact := EXACT_PIN.match(spec):
            pinned.append(PinnedDependency(name, exact.group(1), path, lineno))
        else:
            loose.append(name)
    return pinned, loose


def _line_of(text: str, needle: str) -> int | None:
    index = text.find(needle)
    return text.count("\n", 0, index) + 1 if index >= 0 else None


def _toml_lock(path: str, text: str) -> list[PinnedDependency]:
    """poetry.lock / uv.lock / pdm.lock: `[[package]]` tables with name + version."""
    try:
        packages = tomllib.loads(text).get("package", [])
    except tomllib.TOMLDecodeError:
        return []
    pinned = []
    for package in packages:
        source = package.get("source") or {}
        if not package.get("name") or not package.get("version") or any(key in source for key in LOCAL_SOURCES):
            continue  # the project itself / local path packages are not on PyPI
        line = _line_of(text, f'name = "{package["name"]}"')
        pinned.append(PinnedDependency(normalise(package["name"]), str(package["version"]), path, line))
    return pinned


def _pipfile_lock(path: str, text: str) -> list[PinnedDependency]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return []
    pinned = []
    for section in ("default", "develop"):
        for name, meta in (data.get(section) or {}).items():
            version = str((meta or {}).get("version", "")).lstrip("=")
            if version:
                pinned.append(PinnedDependency(normalise(name), version, path, _line_of(text, f'"{name}"')))
    return pinned


def _pyproject_pins(path: str, text: str) -> tuple[list[PinnedDependency], list[str]]:
    try:
        deps = tomllib.loads(text).get("project", {}).get("dependencies", [])
    except tomllib.TOMLDecodeError:
        return [], []
    return _requirement_lines(path, "\n".join(d for d in deps if isinstance(d, str)))


def _parse_manifest(path: str, text: str) -> tuple[list[PinnedDependency], list[str]] | None:
    """(exact pins, loose names) for a dependency manifest, or None if `path` is not one."""
    name = PurePosixPath(path).name
    if _is_requirements_file(path):
        return _requirement_lines(path, text)
    if name in {"poetry.lock", "uv.lock", "pdm.lock"}:
        return _toml_lock(path, text), []
    if name == "Pipfile.lock":
        return _pipfile_lock(path, text), []
    if name == "pyproject.toml" and path.count("/") <= 1:
        return _pyproject_pins(path, text)
    return None


def collect_dependencies(project: ProjectFiles) -> tuple[list[PinnedDependency], list[str], list[str]]:
    """(exact versions, names without an exact version, manifest files read)."""
    unique: dict[tuple[str, str], PinnedDependency] = {}
    loose: set[str] = set()
    sources: list[str] = []
    for path in sorted(project.texts):
        parsed = _parse_manifest(path, project.texts[path])
        if parsed is None:
            continue
        sources.append(path)
        for dep in parsed[0]:
            unique.setdefault((dep.name, dep.version), dep)
        loose.update(parsed[1])
    exact_names = {dep.name for dep in unique.values()}
    return list(unique.values()), sorted(loose - exact_names), sources


# --- Severity -------------------------------------------------------------------------------

CVSS3_WEIGHTS = {
    "AV": {"N": 0.85, "A": 0.62, "L": 0.55, "P": 0.2},
    "AC": {"L": 0.77, "H": 0.44},
    "UI": {"N": 0.85, "R": 0.62},
    "CIA": {"H": 0.56, "L": 0.22, "N": 0.0},
}


def _roundup(value: float) -> float:
    """CVSS v3.1 round-up to one decimal, robust to floating point noise."""
    integer = round(value * 100000)
    return integer / 100000.0 if integer % 10000 == 0 else (floor(integer / 10000) + 1) / 10.0


def cvss3_base_score(vector: str) -> float | None:
    """Base score of a CVSS v3.x vector string, or None if it cannot be parsed."""
    try:
        metrics = dict(part.split(":", 1) for part in vector.split("/")[1:])
        changed = metrics["S"] == "C"
        privileges = {"N": 0.85, "L": 0.68 if changed else 0.62, "H": 0.5 if changed else 0.27}[metrics["PR"]]
        cia = [CVSS3_WEIGHTS["CIA"][metrics[key]] for key in ("C", "I", "A")]
        exploitability = 8.22 * CVSS3_WEIGHTS["AV"][metrics["AV"]] * CVSS3_WEIGHTS["AC"][metrics["AC"]] * privileges * CVSS3_WEIGHTS["UI"][metrics["UI"]]
    except (KeyError, ValueError):
        return None
    iss = 1 - (1 - cia[0]) * (1 - cia[1]) * (1 - cia[2])
    impact = 7.52 * (iss - 0.029) - 3.25 * (iss - 0.02) ** 15 if changed else 6.42 * iss
    if impact <= 0:
        return 0.0
    return _roundup(min(1.08 * (impact + exploitability) if changed else impact + exploitability, 10))


DATABASE_SEVERITY = {"CRITICAL": "critical", "HIGH": "high", "MODERATE": "medium", "MEDIUM": "medium", "LOW": "low"}


def _cvss_severity(vuln: dict) -> str | None:
    for entry in vuln.get("severity") or []:
        if entry.get("type") != "CVSS_V3" or (score := cvss3_base_score(entry.get("score", ""))) is None:
            continue
        return next(label for limit, label in ((9, "critical"), (7, "high"), (4, "medium"), (0, "low")) if score >= limit)
    return None


def severity_of(vuln: dict) -> str:
    """Advisory severity when reviewed (GHSA), else the CVSS v3 base score, else medium."""
    reviewed = DATABASE_SEVERITY.get(str((vuln.get("database_specific") or {}).get("severity", "")).upper())
    return reviewed or _cvss_severity(vuln) or "medium"


# --- Fixed versions ----------------------------------------------------------------------------

def _version(text: str) -> Version | None:
    try:
        return Version(text)
    except InvalidVersion:
        return None


def _package_ranges(vuln: dict, package: str) -> list[list[dict]]:
    """Event lists of the PyPI ranges that apply to `package`."""
    return [
        rng.get("events") or []
        for affected in vuln.get("affected") or []
        if (affected.get("package") or {}).get("ecosystem") == "PyPI"
        and normalise((affected.get("package") or {}).get("name", "")) == package
        for rng in affected.get("ranges") or []
    ]


def _fixes_covering(events: list[dict], installed: Version) -> list[Version]:
    """`fixed` versions of the introduced→fixed windows that contain `installed`."""
    fixes, introduced = [], None
    for event in events:
        if "introduced" in event:
            introduced = _version(event["introduced"])
        elif "fixed" in event and introduced is not None:
            fixed = _version(event["fixed"])
            if fixed and introduced <= installed < fixed:
                fixes.append(fixed)
    return fixes


def fixed_version(vuln: dict, package: str, current: str) -> str | None:
    """Smallest version that fixes `vuln` for the range `current` falls into."""
    installed = _version(current)
    if installed is None:
        return None
    candidates = [fix for events in _package_ranges(vuln, package) for fix in _fixes_covering(events, installed)]
    return str(min(candidates)) if candidates else None


# --- OSV client -------------------------------------------------------------------------------

_CACHE: dict[tuple[str, str], tuple[float, list[dict]]] = {}


def _post_query(payload: dict) -> dict:
    """One OSV request. Isolated so tests can replace it without touching the network."""
    resp = requests.post(OSV_QUERY_URL, json=payload, timeout=REQUEST_TIMEOUT, headers={"User-Agent": "RepoMentor-AI"})
    if resp.status_code != 200:
        raise OSVError(f"OSV.dev hata döndürdü (HTTP {resp.status_code}).")
    return resp.json()


def query_package(dep: PinnedDependency) -> list[dict]:
    key = (dep.name, dep.version)
    cached = _CACHE.get(key)
    if cached and time.time() - cached[0] < CACHE_SECONDS:
        return cached[1]
    payload: dict = {"package": {"name": dep.name, "ecosystem": "PyPI"}, "version": dep.version}
    vulns: list[dict] = []
    for _ in range(MAX_PAGES):
        data = _post_query(payload)
        vulns += data.get("vulns") or []
        if not data.get("next_page_token"):
            break
        payload["page_token"] = data["next_page_token"]
    _CACHE[key] = (time.time(), vulns)
    return vulns


def query_all(deps: list[PinnedDependency]) -> list[list[dict]]:
    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            return list(pool.map(query_package, deps))
    except requests.Timeout as exc:
        raise OSVError("OSV.dev zamanında yanıt vermedi.") from exc
    except requests.RequestException as exc:
        raise OSVError("OSV.dev'e bağlanılamadı (internet bağlantısını kontrol edin).") from exc
    except ValueError as exc:
        raise OSVError("OSV.dev'den beklenmeyen bir yanıt geldi.") from exc


# --- Building the report ---------------------------------------------------------------------

def _distinct_advisories(vulns: list[dict]) -> list[dict]:
    """The same advisory often appears as GHSA-… and PYSEC-… aliases; keep one (GHSA first)."""
    seen: set[str] = set()
    kept = []
    for vuln in sorted(vulns, key=lambda v: (not v.get("id", "").startswith("GHSA"), v.get("id", ""))):
        ids = {vuln.get("id", "")} | set(vuln.get("aliases") or [])
        if ids & seen:
            continue
        seen |= ids
        kept.append(vuln)
    return kept


def _vulnerability(vuln: dict, dep: PinnedDependency) -> Vulnerability:
    vuln_id = vuln.get("id", "")
    text = (vuln.get("summary") or vuln.get("details") or "").strip()
    return Vulnerability(
        id=vuln_id,
        cve=next((a for a in vuln.get("aliases") or [] if a.startswith("CVE-")), None),
        summary=text.splitlines()[0][:200] if text else "",
        severity=severity_of(vuln),
        fixed=fixed_version(vuln, dep.name, dep.version),
        url=OSV_PAGE_URL.format(id=vuln_id) if VULN_ID.match(vuln_id) else "https://osv.dev",
    )


def _package_report(dep: PinnedDependency, vulns: list[dict]) -> VulnerablePackage:
    items = sorted((_vulnerability(v, dep) for v in _distinct_advisories(vulns)), key=lambda v: SEVERITY_ORDER[v.severity])
    fixes = [version for v in items if v.fixed and (version := _version(v.fixed))]
    return VulnerablePackage(
        name=dep.name, version=dep.version, file=dep.file, line=dep.line,
        severity=items[0].severity,
        fixed_version=str(max(fixes)) if fixes else None,
        vulnerabilities=items,
    )


def _is_major_jump(current: str, target: str | None) -> bool:
    before, after = _version(current), _version(target or "")
    return bool(before and after and after.major > before.major)


def _recommendation(pkg: VulnerablePackage) -> str | None:
    """Override the catalogue text for the cases it cannot express; None keeps the default."""
    if pkg.fixed_version is None:
        return (f"`{pkg.name}` için bu açıkları kapatan bir sürüm henüz yayınlanmamış. Paketin etkilenen özelliğini "
                "kullanıp kullanmadığınızı kontrol edin ve alternatif bir paket değerlendirin.")
    notes = []
    if _is_major_jump(pkg.version, pkg.fixed_version):
        notes.append(f"Bu bir büyük sürüm atlaması ({pkg.version} → {pkg.fixed_version}); geriye dönük uyumsuz değişiklikler "
                     "olabileceği için paketin değişiklik notlarını (changelog) okuyun.")
    if any(v.fixed is None for v in pkg.vulnerabilities):
        notes.append("Bazı açıklar için henüz düzeltme yok; yükselttikten sonra yeniden kontrol edin.")
    if not notes:
        return None
    return (f"`{pkg.name}` paketini en az `{pkg.fixed_version}` sürümüne yükseltin "
            f"(`pip install -U \"{pkg.name}>={pkg.fixed_version}\"`). " + " ".join(notes))


def _effort(pkg: VulnerablePackage) -> int:
    minutes = 15 + 5 * min(len(pkg.vulnerabilities) - 1, 6)
    if pkg.fixed_version is None:
        minutes += 30
    elif _is_major_jump(pkg.version, pkg.fixed_version):
        minutes += 90  # API changes usually need code updates and a test run
    return minutes


def _issue(pkg: VulnerablePackage) -> Issue:
    top = "; ".join(f"{v.id} ({SEVERITY_LABELS[v.severity].lower()}): {v.summary}" for v in pkg.vulnerabilities[:3])
    more = f" ve {len(pkg.vulnerabilities) - 3} açık daha" if len(pkg.vulnerabilities) > 3 else ""
    values = {"name": pkg.name, "version": pkg.version, "count": len(pkg.vulnerabilities),
              "advisories": top + more, "fix": pkg.fixed_version or ""}
    overrides = {"recommendation": text} if (text := _recommendation(pkg)) else {}
    issue = make_issue(
        "DEP001", [Location(pkg.file, pkg.line)], values,
        severity=pkg.severity, source="osv", count=len(pkg.vulnerabilities), effort_minutes=_effort(pkg), **overrides,
    )
    issue.rule_id = f"DEP-{pkg.name}"  # one id per package, so report comparison tracks each package
    return issue


def coverage_text(report: DependencyReport) -> str:
    """One honest sentence about what was (and was not) checked."""
    if not report.enabled:
        return "Kapalı: bu analizde bağımlılıklar sorgulanmadı."
    if report.error:
        return f"Yapılamadı: {report.error}"
    if not report.total:
        return "Bağımlılık dosyası bulunamadı."
    loose = len(report.unpinned)
    unchecked = f"{loose} paket sürümü sabitlenmediği için kontrol edilemedi" if loose else ""
    if not report.checked:
        return f"Sürümü kesin olan bağımlılık yok; {unchecked}."
    found = (f"{len(report.vulnerable)} pakette {report.vulnerability_count} bilinen açık bulundu"
             if report.vulnerable else "bilinen açık bulunmadı")
    parts = [f"{report.checked} paket kontrol edildi, {found}", unchecked]
    if report.skipped:
        parts.append(f"{report.skipped} paket sınır nedeniyle atlandı")
    return "; ".join(p for p in parts if p) + "."


def analyze_dependencies(project: ProjectFiles, enabled: bool = True) -> tuple[DependencyReport, list[Issue]]:
    """Check exact dependency versions against OSV.dev. Never raises; errors land in the report."""
    pinned, loose, sources = collect_dependencies(project)
    report = DependencyReport(enabled=enabled, unpinned=loose, sources=sources, total=len(pinned) + len(loose))
    if not enabled or not pinned:
        return report, []
    if len(pinned) > MAX_PACKAGES:
        report.skipped = len(pinned) - MAX_PACKAGES
        pinned = pinned[:MAX_PACKAGES]
    try:
        results = query_all(pinned)
    except OSVError as exc:
        report.error = str(exc)
        return report, []
    report.ran = True
    report.checked = len(pinned)
    report.vulnerable = sorted(
        (_package_report(dep, vulns) for dep, vulns in zip(pinned, results, strict=True) if vulns),
        key=lambda p: (SEVERITY_ORDER[p.severity], -len(p.vulnerabilities), p.name),
    )
    return report, [_issue(pkg) for pkg in report.vulnerable]
