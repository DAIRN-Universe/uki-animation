"""Manifest validation and content-pinned downloads. No binary assets live in Git."""

from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import yaml


class AssetError(Exception):
    """A safe, user-facing error, without credentials or HTTP response bodies."""


class UniqueLoader(yaml.SafeLoader):
    """Reject duplicate YAML keys instead of silently replacing metadata."""


def _mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise AssetError("Manifest keys must be unique strings.")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


@dataclass(frozen=True)
class Asset:
    id: str
    drive_file_id: str
    path: str
    kind: str
    status: str
    version: str
    sha256: str | None
    size_bytes: int | None
    characters: tuple[str, ...]
    episodes: tuple[str, ...]
    scenes: tuple[str, ...]


def _relative_path(value):
    if (not isinstance(value, str) or not value or "\\" in value
            or ":" in value or any(ord(c) < 32 for c in value)):
        raise AssetError("Asset path must be a relative POSIX file path.")
    parts = value.split("/")
    if any(p in ("", ".", "..") or p.startswith(".") for p in parts):
        raise AssetError("Asset path contains an unsafe component.")
    if PurePosixPath(value).is_absolute():
        raise AssetError("Absolute asset paths are forbidden.")
    return value


def load_manifest(path):
    try:
        data = yaml.load(Path(path).read_text(encoding="utf-8"), Loader=UniqueLoader)
    except (OSError, UnicodeError, yaml.YAMLError, RecursionError) as exc:
        raise AssetError("Cannot read manifest: expected valid UTF-8 YAML.") from exc
    if not isinstance(data, dict) or type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise AssetError("Expected manifest schema_version: 1.")
    if not isinstance(data.get("assets"), list):
        raise AssetError("Expected an assets list.")
    assets, ids, paths = [], set(), set()
    for row in data["assets"]:
        if not isinstance(row, dict):
            raise AssetError("Each asset must be a mapping.")
        for key in ("id", "drive_file_id", "path", "kind", "status", "version", "purpose"):
            if not isinstance(row.get(key), str) or not row[key].strip():
                raise AssetError(f"Asset requires a non-empty string: {key}.")
        if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]*", row["id"]):
            raise AssetError("Invalid asset ID.")
        if row.get("source") != "google_drive" or not re.fullmatch(r"[A-Za-z0-9_-]{10,}", row["drive_file_id"]):
            raise AssetError(f"{row['id']}: expected google_drive and a real file ID.")
        target = _relative_path(row["path"])
        if row["id"] in ids or target.casefold() in paths:
            raise AssetError("Duplicate asset ID or target path.")
        ids.add(row["id"])
        paths.add(target.casefold())
        digest = row.get("sha256")
        if digest is not None and (not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)):
            raise AssetError(f"{row['id']}: SHA-256 must be 64 lowercase hex digits or null.")
        size = row.get("size_bytes")
        if size is not None and (type(size) is not int or size <= 0):
            raise AssetError("size_bytes must be a positive integer or null.")
        tags = []
        for key in ("characters", "episodes", "scenes"):
            values = row.get(key, [])
            if not isinstance(values, list) or any(not isinstance(v, str) or not v for v in values):
                raise AssetError(f"{key} must be a list of non-empty strings.")
            tags.append(tuple(values))
        assets.append(Asset(row["id"], row["drive_file_id"], target, row["kind"],
                            row["status"], row["version"], digest, size, *tags))
    return assets


def select_assets(assets, *, ids=(), character=None, episode=None, scene=None):
    unknown = set(ids) - {a.id for a in assets}
    if unknown:
        raise AssetError("Unknown asset IDs: " + ", ".join(sorted(unknown)))
    selected = [a for a in assets if (not ids or a.id in ids)
                and (character is None or character in a.characters)
                and (episode is None or episode in a.episodes)
                and (scene is None or scene in a.scenes)]
    if not selected:
        raise AssetError("No assets match the filters. Missing scene resources need real Drive IDs.")
    return selected


def asset_target(repo, asset):
    """Reject symlinks even when they currently point inside the cache."""
    repo = Path(repo).resolve()
    root = repo / ".local-assets"
    target = root / _relative_path(asset.path)
    if root.is_symlink():
        raise AssetError(".local-assets must not be a symlink.")
    current = root
    for part in PurePosixPath(asset.path).parts:
        current = current / part
        if current.is_symlink():
            raise AssetError(f"{asset.id}: symlink in asset path.")
    if not target.resolve().is_relative_to(root.resolve()):
        raise AssetError("Asset path escapes .local-assets.")
    return target


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_file(asset, path):
    if asset.sha256 is None:
        raise AssetError(f"{asset.id}: SHA-256 is not pinned; download separately, inspect and register it first.")
    if not Path(path).is_file():
        raise AssetError(f"{asset.id}: local file is missing.")
    if asset.size_bytes is not None and Path(path).stat().st_size != asset.size_bytes:
        raise AssetError(f"{asset.id}: size mismatch; existing files are preserved.")
    if file_hash(path) != asset.sha256:
        raise AssetError(f"{asset.id}: SHA-256 mismatch; existing files are preserved.")


@contextmanager
def cache_lock(repo):
    root = Path(repo).resolve() / ".local-assets"
    if root.is_symlink():
        raise AssetError(".local-assets must not be a symlink.")
    root.mkdir(parents=True, exist_ok=True)
    fd = os.open(root / ".sync.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _install(asset, repo, writer):
    if asset.sha256 is None:
        raise AssetError(f"{asset.id}: SHA-256 is not pinned; no download attempted.")
    target = asset_target(repo, asset)
    if target.exists():
        verify_file(asset, target)
        return "verified"
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".asset-", dir=target.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as destination:
            writer(destination)
            destination.flush()
            os.fsync(destination.fileno())
        verify_file(asset, temporary)
        # Hard-link publication is atomic and cannot overwrite a file created meanwhile.
        asset_target(repo, asset)
        try:
            os.link(temporary, target)
        except FileExistsError as exc:
            raise AssetError(f"{asset.id}: destination appeared during download; preserved.") from exc
    finally:
        temporary.unlink(missing_ok=True)
    return "installed"


def import_file(asset, repo, source):
    """Adopt a connector download, verifying exactly the same pinned bytes."""
    source = Path(source)
    verify_file(asset, source)
    def copy(destination):
        with source.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                destination.write(chunk)
    return _install(asset, repo, copy)


def google_token(credentials_path):
    """Read only a user-chosen local credential file. Never log token or provider errors."""
    if not credentials_path:
        raise AssetError("Set --credentials or UKI_GOOGLE_CREDENTIALS to a local OAuth/service-account JSON file.")
    try:
        import google.auth
        from google.auth.transport.requests import Request as AuthRequest
        info = json.loads(Path(credentials_path).read_text(encoding="utf-8"))
        if info.get("type") not in ("authorized_user", "service_account"):
            raise ValueError("Unsupported credentials")
        credentials, _ = google.auth.load_credentials_from_dict(
            info, scopes=["https://www.googleapis.com/auth/drive.readonly"])
        credentials.refresh(AuthRequest())
        return credentials.token
    except ImportError as exc:
        raise AssetError("Install requirements-assets.txt for Google Drive authentication.") from exc
    except Exception as exc:
        raise AssetError("Google authorization failed. Check your local credentials and read access.") from exc


def download_file(asset, repo, token_provider):
    def download(destination):
        token = token_provider()
        request = Request(
            f"https://www.googleapis.com/drive/v3/files/{asset.drive_file_id}?alt=media&supportsAllDrives=true",
            headers={"Authorization": f"Bearer {token}"})
        try:
            with urlopen(request, timeout=60) as response:
                total = 0
                while chunk := response.read(1024 * 1024):
                    total += len(chunk)
                    if asset.size_bytes is not None and total > asset.size_bytes:
                        raise AssetError(f"{asset.id}: download exceeds pinned size; version may have changed.")
                    destination.write(chunk)
        except HTTPError as exc:
            if exc.code in (401, 403):
                message = "authorization denied; check Drive read access"
            elif exc.code == 404:
                message = "file missing or not shared with this account"
            else:
                message = f"Drive HTTP {exc.code}; retry later"
            raise AssetError(f"{asset.id}: {message}.") from None
        except (URLError, TimeoutError, ConnectionError) as exc:
            raise AssetError(f"{asset.id}: network download failed; retry later.") from None
    return _install(asset, repo, download)
