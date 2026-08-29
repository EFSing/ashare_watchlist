import shutil

from core_signal_replay import REQUIRED_RAW_INPUTS, _source_metadata, canonical_source_content_sha256


def _write_raw_fixture(root):
    for role, filename in REQUIRED_RAW_INPUTS:
        path = root / filename
        path.write_bytes(f"{role}\nraw fixture\n".encode("utf-8"))


def test_canonical_raw_source_hash_is_independent_of_root_directory(tmp_path):
    first = tmp_path / "first-root"
    second = tmp_path / "second-root"
    first.mkdir()
    second.mkdir()
    _write_raw_fixture(first)
    for _, filename in REQUIRED_RAW_INPUTS:
        shutil.copyfile(first / filename, second / filename)

    first_metadata = _source_metadata(first)
    second_metadata = _source_metadata(second)

    assert first_metadata["content_sha256"] == second_metadata["content_sha256"]
    assert canonical_source_content_sha256(reversed(first_metadata["files"])) == first_metadata["content_sha256"]
    assert [item["path"] for item in first_metadata["files"]] != [
        item["path"] for item in second_metadata["files"]
    ]


def test_canonical_raw_source_hash_changes_when_any_file_bytes_change(tmp_path):
    original = tmp_path / "original-root"
    changed = tmp_path / "changed-root"
    original.mkdir()
    changed.mkdir()
    _write_raw_fixture(original)
    for _, filename in REQUIRED_RAW_INPUTS:
        shutil.copyfile(original / filename, changed / filename)

    before = _source_metadata(changed)["content_sha256"]
    changed_path = changed / REQUIRED_RAW_INPUTS[-1][1]
    changed_path.write_bytes(changed_path.read_bytes() + b"changed byte")

    assert _source_metadata(changed)["content_sha256"] != before
