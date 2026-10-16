import io
import stat
import zipfile

import pytest
import requests

from repomentor.analyzer.repository_loader import (
    LoaderError,
    download_github_archive,
    load_github,
    load_zip,
    parse_github_url,
    project_root,
    safe_extract_zip,
)


def make_zip(entries: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return buffer.getvalue()


@pytest.mark.parametrize("evil", ["../evil.py", "a/../../evil.py", "/etc/evil.py", "C:/evil.py"])
def test_zip_slip_is_rejected(tmp_path, evil):
    with pytest.raises(LoaderError, match="ZIP Slip"):
        safe_extract_zip(make_zip({evil: "x"}), tmp_path)
    assert not (tmp_path.parent / "evil.py").exists()


def test_symlinks_are_skipped(tmp_path):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        link = zipfile.ZipInfo("link")
        link.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(link, "/etc/passwd")
        archive.writestr("ok.py", "print(1)")
    safe_extract_zip(buffer.getvalue(), tmp_path)
    assert (tmp_path / "ok.py").exists()
    assert not (tmp_path / "link").exists()


def test_bad_zip_has_friendly_error(tmp_path):
    with pytest.raises(LoaderError, match="ZIP"):
        safe_extract_zip(b"not a zip", tmp_path)


def test_zip_bomb_guard(tmp_path, monkeypatch):
    monkeypatch.setattr("repomentor.analyzer.repository_loader.MAX_UNCOMPRESSED_BYTES", 10)
    with pytest.raises(LoaderError, match="boyut"):
        safe_extract_zip(make_zip({"big.txt": "x" * 100}), tmp_path)


def test_single_top_folder_is_unwrapped(tmp_path):
    safe_extract_zip(make_zip({"repo-main/app.py": "x", "repo-main/README.md": "y"}), tmp_path)
    assert project_root(tmp_path).name == "repo-main"


def test_load_zip_cleans_up_temp_folder():
    with load_zip(make_zip({"proj/app.py": "print(1)"}), "proj.zip") as loaded:
        root = loaded.root
        assert (root / "app.py").exists()
    assert not root.exists()


@pytest.mark.parametrize(
    ("url", "owner", "repo", "ref", "subpath"),
    [
        ("https://github.com/octo/hello", "octo", "hello", None, None),
        ("github.com/octo/hello.git", "octo", "hello", None, None),
        ("https://github.com/octo/hello/tree/dev/src/app", "octo", "hello", "dev", "src/app"),
        ("https://www.github.com/octo/hello/", "octo", "hello", None, None),
    ],
)
def test_parse_github_url(url, owner, repo, ref, subpath):
    parsed = parse_github_url(url)
    assert (parsed.owner, parsed.repo, parsed.ref, parsed.subpath) == (owner, repo, ref, subpath)


@pytest.mark.parametrize("url", ["https://gitlab.com/a/b", "github.com/only-owner", "not a url"])
def test_parse_github_url_rejects_other_hosts(url):
    with pytest.raises(LoaderError):
        parse_github_url(url)


def test_github_report_preserves_branch_and_subdirectory(monkeypatch):
    monkeypatch.setattr("repomentor.analyzer.repository_loader.fetch_github_metadata", lambda ref: {})
    monkeypatch.setattr("repomentor.analyzer.repository_loader.download_github_archive",
                        lambda ref, branch: make_zip({"repo-dev/src/app.py": "print(1)"}))
    with load_github("https://github.com/octo/repo/tree/dev/src") as loaded:
        assert loaded.source_url == "https://github.com/octo/repo/tree/dev/src"
        assert loaded.name == "repo/src"
        assert (loaded.root / "app.py").is_file()


def test_interrupted_github_download_has_friendly_error_and_closes_connection(monkeypatch):
    class InterruptedResponse:
        status_code = 200
        closed = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.closed = True

        def iter_content(self, chunk_size):
            yield b"partial"
            raise requests.exceptions.ChunkedEncodingError("connection lost")

    response = InterruptedResponse()
    monkeypatch.setattr("repomentor.analyzer.repository_loader.requests.get", lambda *args, **kwargs: response)
    with pytest.raises(LoaderError, match="indirmesi kesildi"):
        download_github_archive(parse_github_url("https://github.com/octo/repo"), "main")
    assert response.closed
