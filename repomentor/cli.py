"""Command line entry point: `python -m repomentor <path|github-url>`."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from repomentor.ai.providers import PROVIDERS, LLMConfig, list_models, resolve_api_key
from repomentor.analyzer.pipeline import analyze_project
from repomentor.analyzer.pr_report import build_pr_comment
from repomentor.analyzer.report_builder import build_csv, build_json, build_markdown
from repomentor.analyzer.repository_loader import LoaderError, load_github, load_local, load_zip
from repomentor.models.analysis_result import AnalysisResult


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="repomentor", description="Python projelerini analiz eder ve rapor üretir.")
    parser.add_argument("target", help="Klasör yolu, .zip dosyası veya public GitHub adresi")
    parser.add_argument("--ai", choices=sorted(PROVIDERS), help="Yapay zekâ sağlayıcısı (varsayılan: kapalı)")
    parser.add_argument("--model", help="Model adı (varsayılan: sağlayıcının önerdiği / ilk uygun model)")
    parser.add_argument("--format", choices=["md", "json", "csv", "pr"], default="md",
                        help="pr: pull request yorumu için kısa özet (--baseline ile skor farkı ve yeni bulgular)")
    parser.add_argument("-o", "--output", help="Raporu dosyaya yaz (varsayılan: stdout)")
    parser.add_argument("--baseline", metavar="HEDEF", help="Karşılaştırılacak önceki sürüm: klasör, .zip veya GitHub adresi")
    parser.add_argument("--min-score", type=int, help="Skor bu değerin altındaysa 1 ile çık (CI için)")
    parser.add_argument("--max-drop", type=int, help="Skor --baseline'a göre bu kadardan fazla düşerse 1 ile çık")
    parser.add_argument("--no-osv", action="store_true", help="Bağımlılık açığı taramasını kapat (OSV.dev'e istek gönderilmez)")
    parser.add_argument("--fix-patch", metavar="DOSYA", help="Güvenli otomatik düzeltmeleri bu dosyaya yama olarak yaz (proje dosyalarına dokunulmaz)")
    return parser


def _loader(target: str):
    if target.startswith(("http://", "https://", "github.com/")):
        return load_github(target)
    if target.endswith(".zip"):
        return load_zip(Path(target).read_bytes(), Path(target).name)
    return load_local(target)


def _analyze(target: str, llm: LLMConfig | None, check_dependencies: bool, label: str = "") -> AnalysisResult:
    with _loader(target) as loaded:
        progress = lambda message, _: print(f"• {label}{message}", file=sys.stderr)  # noqa: E731
        return analyze_project(loaded, llm=llm, progress=progress, check_dependencies=check_dependencies)


def _llm(args: argparse.Namespace) -> LLMConfig | None:
    if not args.ai:
        return None
    key = resolve_api_key(args.ai)
    model = args.model or next(iter(list_models(args.ai, key)), PROVIDERS[args.ai].default_model)
    return LLMConfig(provider=args.ai, model=model, api_key=key)


def _gates(args: argparse.Namespace, result: AnalysisResult, baseline: AnalysisResult | None) -> list[tuple[str, bool]]:
    """(description, passed) for each quality gate the user asked for."""
    gates = []
    if args.min_score is not None:
        gates.append((f"Skor en az {args.min_score} olmalı: {result.score.overall}", result.score.overall >= args.min_score))
    if args.max_drop is not None and baseline is not None:
        drop = baseline.score.overall - result.score.overall
        gates.append((f"Skor en fazla {args.max_drop} puan düşebilir: {max(drop, 0)} puan düştü", drop <= args.max_drop))
    return gates


def _report(args: argparse.Namespace, result: AnalysisResult, baseline: AnalysisResult | None, gates: list) -> str:
    if args.format == "pr":
        return build_pr_comment(result, baseline, gates)
    return {"md": build_markdown, "json": build_json, "csv": build_csv}[args.format](result)


def _write_patch(result: AnalysisResult, path: str) -> None:
    if not result.fixes.files:
        print("Otomatik düzeltilebilecek bir sorun bulunamadı; yama yazılmadı.", file=sys.stderr)
        return
    Path(path).write_text(result.fixes.patch, encoding="utf-8", newline="")
    print(f"Düzeltme yaması yazıldı: {path} ({result.fixes.change_count} değişiklik, {len(result.fixes.files)} dosya). "
          f"İnceleyip `git apply {path}` ile uygulayın.", file=sys.stderr)


def _github_outputs(result: AnalysisResult, baseline: AnalysisResult | None) -> None:
    """Inside GitHub Actions, expose the score as step outputs."""
    if path := os.getenv("GITHUB_OUTPUT"):
        delta = result.score.overall - baseline.score.overall if baseline else 0
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"score={result.score.overall}\nscore-delta={delta}\n")


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.max_drop is not None and not args.baseline:
        print("Hata: --max-drop için karşılaştırılacak sürümü --baseline ile verin.", file=sys.stderr)
        return 2
    llm, check = _llm(args), not args.no_osv
    try:
        baseline = _analyze(args.baseline, llm, check, label="[önceki] ") if args.baseline else None
        result = _analyze(args.target, llm, check)
    except LoaderError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 2

    gates = _gates(args, result, baseline)
    report = _report(args, result, baseline, gates)
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8", newline="")
        print(f"Rapor yazıldı: {args.output} (skor {result.score.overall}/100)", file=sys.stderr)
    else:
        print(report)
    if args.fix_patch:
        _write_patch(result, args.fix_patch)
    _github_outputs(result, baseline)
    failed = [label for label, passed in gates if not passed]
    for label in failed:
        print(f"Kalite kapısı geçilemedi: {label}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
