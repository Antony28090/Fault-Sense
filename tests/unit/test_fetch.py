import hashlib

from faultsense.fetch import fetch_manuals, sha256_file
from faultsense.manifest import ManualSpec

PAYLOAD = b"%PDF-1.7 fake manual"


def _spec(sha: str) -> ManualSpec:
    return ManualSpec(
        id="m1", family="ATVX", title="Test", doc_ref="D1", version="01", file="m1.pdf",
        url="https://example.invalid/m1.pdf", sha256=sha, fault_layout="block",
        fault_pages=(1, 2), index_pages=None, safety_pages=[1],
    )


def _fake_downloader(calls):
    def download(url, dest):
        calls.append(url)
        dest.write_bytes(PAYLOAD)
    return download


def test_downloads_missing_manual_and_verifies_checksum(tmp_path):
    calls = []
    spec = _spec(hashlib.sha256(PAYLOAD).hexdigest())
    assert fetch_manuals([spec], tmp_path, _fake_downloader(calls)) == [("m1", "downloaded")]
    assert calls == ["https://example.invalid/m1.pdf"]
    assert sha256_file(tmp_path / "m1.pdf") == spec.sha256


def test_present_manual_is_not_downloaded_again(tmp_path):
    (tmp_path / "m1.pdf").write_bytes(PAYLOAD)
    calls = []
    spec = _spec(hashlib.sha256(PAYLOAD).hexdigest())
    assert fetch_manuals([spec], tmp_path, _fake_downloader(calls)) == [("m1", "present")]
    assert calls == []


def test_checksum_mismatch_is_reported(tmp_path):
    spec = _spec("0" * 64)
    assert fetch_manuals([spec], tmp_path, _fake_downloader([])) == [("m1", "checksum-mismatch")]
