"""Command line entry point: `python -m repomentor <path|github-url>`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from repomentor.ai.providers import PROVIDERS, LLMConfig, list_models, resolve_api_key
from repomentor.analyzer.pipeline import analyze_project
from repomentor.analyzer.report_builder import build_csv, build_json, build_markdown
from repomentor.analyzer.repository_loader import LoaderError, load_github, load_local, load_zip


def _write_patch(result, path: str) -> None:
    if not result.fixes.files:
        print("Otomatik düzeltilebilecek bir sorun bulunamadı; yama yazılmadı.", file=sys.stderr)
        return
    Path(path).write_text(result.fixes.patch, encoding="utf-8", newline="")
    print(f"Düzeltme yaması yazıldı: {path} ({result.fixes.change_count} değişiklik, {len(result.fixes.files)} dosya). "
          f"İnceleyip `git apply {path}` ile uygulayın.", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="repomentor", description="Python projelerini analiz eder ve rapor üretir.")
    parser.add_argument("target", help="Klasör yolu, .zip dosyası veya public GitHub adresi")
    parser.add_argument("--ai", choices=sorted(PROVIDERS), help="Yapay zekâ sağlayıcısı (varsayılan: kapalı)")
    parser.add_argument("--model", help="Model adı (varsayılan: sağlayıcının önerdiği / ilk uygun model)")
    parser.add_argument("--format", choices=["md", "json", "csv"], default="md")
    parser.add_argument("-o", "--output", help="Raporu dosyaya yaz (varsayılan: stdout)")
    parser.add_argument("--min-score", type=int, help="Skor bu değerin altındaysa 1 ile çık (CI için)")
    parser.add_argument("--no-osv", action="store_true", help="Bağımlılık açığı taramasını kapat (OSV.dev'e istek gönderilmez)")
    parser.add_argument("--fix-patch", metavar="DOSYA", help="Güvenli otomatik düzeltmeleri bu dosyaya yama olarak yaz (proje dosyalarına dokunulmaz)")
    args = parser.parse_args(argv)

    llm = None
    if args.ai:
        key = resolve_api_key(args.ai)
        model = args.model or next(iter(list_models(args.ai, key)), PROVIDERS[args.ai].default_model)
        llm = LLMConfig(provider=args.ai, model=model, api_key=key)

    target = args.target
    try:
        if target.startswith(("http://", "https://", "github.com/")):
            loader = load_github(target)
        elif target.endswith(".zip"):
            loader = load_zip(Path(target).read_bytes(), Path(target).name)
        else:
            loader = load_local(target)
        with loader as loaded:
            progress = lambda message, _: print(f"• {message}", file=sys.stderr)  # noqa: E731
            result = analyze_project(loaded, llm=llm, progress=progress, check_dependencies=not args.no_osv)
    except LoaderError as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return 2

    report = {"md": build_markdown, "json": build_json, "csv": build_csv}[args.format](result)
    if args.output:
        Path(args.output).write_text(report, encoding="utf-8", newline="")
        print(f"Rapor yazıldı: {args.output} (skor {result.score.overall}/100)", file=sys.stderr)
    else:
        print(report)
    if args.fix_patch:
        _write_patch(result, args.fix_patch)
    if args.min_score is not None and result.score.overall < args.min_score:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
