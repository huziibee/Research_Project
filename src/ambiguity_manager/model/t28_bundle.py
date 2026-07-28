"""Binary-safe, content-addressed T28 frozen-input bundle utilities."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tarfile
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Mapping


class T28BundleError(ValueError):
    pass


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def binary_stats(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    try:
        data.decode("utf-8")
        utf8 = True
    except UnicodeDecodeError:
        utf8 = False
    return {
        "path": str(path.resolve()), "byte_size": len(data),
        "sha256": sha256_bytes(data), "line_count": data.count(b"\n"),
        "lf_count": data.count(b"\n"), "crlf_count": data.count(b"\r\n"),
        "standalone_cr_count": sum(1 for i, value in enumerate(data) if value == 13 and (i + 1 >= len(data) or data[i + 1] != 10)),
        "final_byte": data[-1] if data else None, "ends_in_lf": data.endswith(b"\n"),
        "utf8_valid": utf8, "bom": data.startswith(b"\xef\xbb\xbf"),
        "first_64_hex": data[:64].hex(), "last_64_hex": data[-64:].hex(),
    }


def first_difference(left: bytes, right: bytes, radius: int = 32) -> dict[str, Any] | None:
    if left == right:
        return None
    offset = next((i for i, (a, b) in enumerate(zip(left, right)) if a != b), min(len(left), len(right)))
    start = max(0, offset - radius)
    end = min(max(len(left), len(right)), offset + radius)
    return {"offset": offset, "left_hex": left[start:end].hex(), "right_hex": right[start:end].hex(), "left_size": len(left), "right_size": len(right)}


def _safe_member_name(name: str) -> str:
    p = PurePosixPath(name)
    if p.is_absolute() or ".." in p.parts or "\\" in name or not name or name.endswith("/"):
        raise T28BundleError(f"unsafe_archive_member:{name}")
    return str(p)


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def build_manifest(root: Path, files: list[tuple[str, str, str | None]]) -> dict[str, Any]:
    members = []
    for relative, role, expected_count in files:
        path = root / Path(relative)
        if not path.is_file():
            raise T28BundleError(f"required_file_missing:{relative}")
        item: dict[str, Any] = {"path": relative.replace(os.sep, "/"), "role": role, "byte_size": path.stat().st_size, "sha256": sha256_file(path)}
        if expected_count is not None:
            item["expected_record_count"] = expected_count
        members.append(item)
    return {"format": "t28-frozen-inputs-v1", "immutable": True, "members": members, "protected_data_loaded": 0, "source_holdout_loaded": 0, "extra_members_allowed": False}


def write_deterministic_tar_gz(archive: Path, root: Path, manifest_bytes: bytes, manifest_name: str, members: list[Mapping[str, Any]]) -> None:
    if archive.exists():
        raise T28BundleError(f"archive_exists:{archive}")
    archive.parent.mkdir(parents=True, exist_ok=True)
    with archive.open("wb") as raw:
        import gzip
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz:
            with tarfile.open(fileobj=gz, mode="w|", format=tarfile.PAX_FORMAT) as tar:
                entries = [(manifest_name, manifest_bytes)] + [(str(item["path"]), (root / Path(str(item["path"]))).read_bytes()) for item in members]
                for name, data in sorted(entries, key=lambda pair: pair[0]):
                    info = tarfile.TarInfo(name=name)
                    info.size = len(data); info.mtime = 0; info.uid = 0; info.gid = 0; info.uname = ""; info.gname = ""; info.mode = 0o444
                    tar.addfile(info, __import__("io").BytesIO(data))


def verify_archive(archive: Path, expected_archive_sha256: str | None, manifest: Mapping[str, Any]) -> dict[str, Any]:
    actual_archive_sha256 = sha256_file(archive)
    if expected_archive_sha256 and actual_archive_sha256 != expected_archive_sha256:
        raise T28BundleError("archive_hash_mismatch")
    expected = {str(item["path"]): item for item in manifest["members"]}
    seen: dict[str, str] = {}
    embedded_manifest_seen = False
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            name = _safe_member_name(member.name)
            if member.issym() or member.islnk() or not member.isfile():
                raise T28BundleError(f"non_regular_archive_member:{name}")
            if name == "bundle_manifest.json":
                data = tar.extractfile(member).read()
                if data != canonical_json(manifest):
                    raise T28BundleError("embedded_manifest_mismatch")
                embedded_manifest_seen = True
                continue
            if name not in expected or name in seen:
                raise T28BundleError(f"unexpected_archive_member:{name}")
            data = tar.extractfile(member).read()
            seen[name] = sha256_bytes(data)
            if seen[name] != expected[name]["sha256"] or len(data) != expected[name]["byte_size"]:
                raise T28BundleError(f"member_hash_mismatch:{name}")
    if not embedded_manifest_seen:
        raise T28BundleError("embedded_manifest_missing")
    if set(seen) != set(expected):
        raise T28BundleError("required_member_missing")
    return {"status": "VERIFY_PASSED", "archive_sha256": actual_archive_sha256, "members": seen}


def safe_extract(archive: Path, destination: Path, manifest: Mapping[str, Any], archive_sha256: str) -> dict[str, Any]:
    if destination.exists():
        raise T28BundleError("extraction_destination_exists")
    verify_archive(archive, archive_sha256, manifest)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=f".{destination.name}.", dir=destination.parent))
    try:
        with tarfile.open(archive, "r:gz") as tar:
            for member in tar.getmembers():
                name = _safe_member_name(member.name)
                if name == "bundle_manifest.json":
                    continue
                out = temp / Path(name)
                out.parent.mkdir(parents=True, exist_ok=True)
                data = tar.extractfile(member).read()
                with out.open("xb") as handle:
                    handle.write(data); handle.flush(); os.fsync(handle.fileno())
        verify_archive(archive, archive_sha256, manifest)
        for item in manifest["members"]:
            out = temp / Path(str(item["path"]))
            if sha256_file(out) != item["sha256"]:
                raise T28BundleError(f"extracted_hash_mismatch:{item['path']}")
            out.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        for directory in sorted((p for p in temp.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            directory.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        temp.chmod(stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH)
        (temp / "VERIFY_PASSED.json").write_bytes(canonical_json({"status": "VERIFY_PASSED", "archive_sha256": archive_sha256, "members": manifest["members"]}))
        os.replace(temp, destination)
        return {"status": "VERIFY_PASSED", "destination": str(destination), "archive_sha256": archive_sha256}
    except Exception:
        shutil.rmtree(temp, ignore_errors=True)
        raise
