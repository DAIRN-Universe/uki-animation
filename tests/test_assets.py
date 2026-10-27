"""Network-free regression checks for immutable asset synchronization."""

from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import yaml

from pipeline.assets.__main__ import main
from pipeline.assets.core import (AssetError, asset_target, cache_lock, download_file,
                                  google_token, import_file, load_manifest,
                                  select_assets, verify_file)
from pipeline.krita.install_brushes import install


CONTENT = b"test fixture, not a real artwork"


def record(**changes):
    row = dict(id="uki.fixture", source="google_drive", drive_file_id="fixture_ID_12345",
               path="characters/uki/fixture.kra", kind="test_fixture", purpose="test only",
               status="test", version="v1", sha256=hashlib.sha256(CONTENT).hexdigest(),
               size_bytes=len(CONTENT), characters=["uki"], episodes=["ep01"], scenes=["sc04"])
    row.update(changes)
    return row


class AssetTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = Path(self.tmp.name)
        self.manifest = self.repo / "assets/manifest.yaml"
        self.manifest.parent.mkdir()
        self.write_manifest([record()])
        self.asset = load_manifest(self.manifest)[0]
        self.token = Mock(return_value="secret-do-not-print")

    def write_manifest(self, rows):
        self.manifest.write_text(yaml.safe_dump(dict(schema_version=1, assets=rows)), encoding="utf-8")

    def response(self, content=CONTENT):
        return patch("pipeline.assets.core.urlopen", return_value=io.BytesIO(content))

    def test_manifest_and_filters(self):
        assets = load_manifest(self.manifest)
        self.assertEqual(select_assets(assets, character="uki", episode="ep01", scene="sc04"), assets)
        for filters in ({"ids": ["missing"]}, {"character": "kirpi"}, {"scene": "sc00"}):
            with self.subTest(filters=filters), self.assertRaises(AssetError):
                select_assets(assets, **filters)

    def test_bad_paths_are_rejected_before_download(self):
        for path in ("../escape.kra", "/tmp/a", "a/../../b", "a\\b", "a//b", "a/./b", "a/", "C:/a", ".sync.lock", "a\nfile"):
            with self.subTest(path=path), self.assertRaises(AssetError):
                self.write_manifest([record(path=path)])
                load_manifest(self.manifest)

    def test_invalid_field_types_and_values(self):
        for change in ({"size_bytes": True}, {"size_bytes": -1}, {"sha256": "fake"},
                       {"version": 7}, {"drive_file_id": "bad id"}, {"source": "url"},
                       {"characters": "uki"}, {"id": "BAD ID"}, {"purpose": ""}):
            with self.subTest(change=change), self.assertRaises(AssetError):
                self.write_manifest([record(**change)])
                load_manifest(self.manifest)

    def test_duplicate_ids_and_paths(self):
        for second in (record(path="another.kra"), record(id="another"),
                       record(id="another", path="CHARACTERS/UKI/FIXTURE.KRA")):
            with self.subTest(second=second), self.assertRaises(AssetError):
                self.write_manifest([record(), second])
                load_manifest(self.manifest)

    def test_duplicate_yaml_keys_and_unsafe_tags(self):
        for text in ("schema_version: 1\nschema_version: 2\nassets: []", "!!python/object:builtins.object {}", "[broken"):
            self.manifest.write_text(text)
            with self.subTest(text=text), self.assertRaises(AssetError):
                load_manifest(self.manifest)

    def test_schema_version(self):
        for text in ("null", "schema_version: true\nassets: []", "schema_version: 2\nassets: []"):
            self.manifest.write_text(text)
            with self.assertRaises(AssetError):
                load_manifest(self.manifest)

    def test_download_then_repeat_without_auth_or_network(self):
        with self.response() as network:
            self.assertEqual(download_file(self.asset, self.repo, self.token), "installed")
            request = network.call_args.args[0]
            self.assertEqual(request.get_header("Authorization"), "Bearer secret-do-not-print")
            self.assertIn("alt=media", request.full_url)
        self.token.reset_mock()
        with patch("pipeline.assets.core.urlopen") as network:
            self.assertEqual(download_file(self.asset, self.repo, self.token), "verified")
            network.assert_not_called()
            self.token.assert_not_called()
        self.assertEqual(asset_target(self.repo, self.asset).read_bytes(), CONTENT)

    def test_changed_local_original_is_never_overwritten(self):
        with self.response():
            download_file(self.asset, self.repo, self.token)
        target = asset_target(self.repo, self.asset)
        target.write_bytes(b"local edits")
        with patch("pipeline.assets.core.urlopen") as network, self.assertRaises(AssetError):
            download_file(self.asset, self.repo, self.token)
        network.assert_not_called()
        self.assertEqual(target.read_bytes(), b"local edits")

    def test_new_manifest_version_cannot_silently_replace_old_file(self):
        with self.response():
            download_file(self.asset, self.repo, self.token)
        new = replace(self.asset, version="v2", sha256="a" * 64)
        with self.assertRaises(AssetError):
            download_file(new, self.repo, self.token)
        self.assertEqual(asset_target(self.repo, self.asset).read_bytes(), CONTENT)

    def test_remote_change_and_truncated_download_leave_no_file(self):
        for content in (b"x" * len(CONTENT), CONTENT[:-1], CONTENT + b"too long"):
            with self.subTest(content=content), self.response(content), self.assertRaises(AssetError):
                download_file(self.asset, self.repo, self.token)
            target = asset_target(self.repo, self.asset)
            self.assertFalse(target.exists())
            self.assertEqual(list(target.parent.glob(".asset-*")), [])

    def test_hash_not_pinned_refuses_network(self):
        with patch("pipeline.assets.core.urlopen") as network, self.assertRaises(AssetError):
            download_file(replace(self.asset, sha256=None), self.repo, self.token)
        network.assert_not_called()
        self.token.assert_not_called()

    def test_root_and_nested_symlinks_are_rejected(self):
        outside = self.repo / "outside"
        outside.mkdir()
        root = self.repo / ".local-assets"
        root.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(AssetError):
            asset_target(self.repo, self.asset)
        with self.assertRaises(AssetError), cache_lock(self.repo):
            pass
        root.unlink()
        root.mkdir()
        (root / "characters").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(AssetError):
            asset_target(self.repo, self.asset)

    def test_atomic_publish_preserves_file_created_during_download(self):
        target = asset_target(self.repo, self.asset)
        def racing_link(source, destination):
            target.write_bytes(b"concurrent original")
            raise FileExistsError()
        with self.response(), patch("pipeline.assets.core.os.link", side_effect=racing_link), self.assertRaises(AssetError):
            download_file(self.asset, self.repo, self.token)
        self.assertEqual(target.read_bytes(), b"concurrent original")

    def test_http_and_network_errors_are_sanitized(self):
        for error in [HTTPError("secret URL", code, "secret token", {}, None) for code in (401, 403, 404, 429, 500)] + [URLError("secret"), TimeoutError("secret")]:
            with self.subTest(error=type(error)), patch("pipeline.assets.core.urlopen", side_effect=error):
                with self.assertRaises(AssetError) as caught:
                    download_file(self.asset, self.repo, self.token)
                self.assertNotIn("secret", str(caught.exception))
            target = asset_target(self.repo, self.asset)
            self.assertFalse(target.exists())
            self.assertEqual(list(target.parent.glob(".asset-*")), [])

    def test_missing_credentials(self):
        with self.assertRaisesRegex(AssetError, "credentials"):
            google_token(None)

    def test_credential_refresh_is_scoped_and_returns_token(self):
        path = self.repo / "credentials.json"
        path.write_text(json.dumps({"type": "authorized_user", "refresh_token": "fixture-secret"}))
        credentials = Mock(token="fixture-access-token")
        with patch("google.auth.load_credentials_from_dict", return_value=(credentials, None)) as load:
            self.assertEqual(google_token(path), "fixture-access-token")
        self.assertEqual(load.call_args.kwargs["scopes"], ["https://www.googleapis.com/auth/drive.readonly"])
        credentials.refresh.assert_called_once()

    def test_credential_failure_is_sanitized(self):
        path = self.repo / "credentials.json"
        path.write_text(json.dumps({"type": "authorized_user"}))
        with patch("google.auth.load_credentials_from_dict", side_effect=ValueError("secret-provider-body")):
            with self.assertRaises(AssetError) as error:
                google_token(path)
        self.assertNotIn("secret-provider-body", str(error.exception))

    def test_auth_failure_does_not_install_file(self):
        self.token.side_effect = AssetError("Google authorization failed.")
        with self.assertRaises(AssetError):
            download_file(self.asset, self.repo, self.token)
        target = asset_target(self.repo, self.asset)
        self.assertFalse(target.exists())
        self.assertEqual(list(target.parent.glob(".asset-*")), [])

    def test_connector_import_checks_hash(self):
        source = self.repo / "downloaded.kra"
        source.write_bytes(CONTENT)
        self.assertEqual(import_file(self.asset, self.repo, source), "installed")
        verify_file(self.asset, asset_target(self.repo, self.asset))
        source.write_bytes(b"wrong data")
        with self.assertRaises(AssetError):
            import_file(self.asset, self.repo, source)

    def test_cli_sync_verify_and_error_exit(self):
        base = ["--manifest", str(self.manifest)]
        with self.response(), patch("pipeline.assets.__main__.google_token", return_value="secret"), redirect_stdout(io.StringIO()):
            self.assertEqual(main(base + ["sync", "--episode", "ep01"]), 0)
            self.assertEqual(main(base + ["verify", "--character", "uki"]), 0)
        error = io.StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(base + ["verify", "--scene", "sc00"]), 1)
        self.assertNotIn("secret", error.getvalue())

    def test_cli_import_requires_single_explicit_id(self):
        with redirect_stderr(io.StringIO()):
            self.assertEqual(main(["--manifest", str(self.manifest), "import", "--file", "missing"]), 1)


class BrushInstallTests(unittest.TestCase):
    def test_inspect_install_and_repeat(self):
        with tempfile.TemporaryDirectory() as tmp, redirect_stdout(io.StringIO()):
            root = Path(tmp)
            resources = {"brushes/a.png": b"fixture", "paintoppresets/a.kpp": b"fixture preset"}
            install(resources, root)
            self.assertEqual(list(root.iterdir()), [])
            install(resources, root, apply=True)
            install(resources, root, apply=True)
            self.assertEqual((root / "brushes/a.png").read_bytes(), b"fixture")

    def test_all_conflicts_checked_before_writing(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "brushes").mkdir()
            (root / "brushes/a.png").write_bytes(b"original")
            with self.assertRaises(AssetError):
                install({"paintoppresets/new.kpp": b"new", "brushes/a.png": b"different"}, root, apply=True)
            self.assertFalse((root / "paintoppresets/new.kpp").exists())
            self.assertEqual((root / "brushes/a.png").read_bytes(), b"original")


if __name__ == "__main__":
    unittest.main()
