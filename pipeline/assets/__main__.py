"""Run from the repository root: python -m pipeline.assets --help."""

import argparse
import os
from pathlib import Path
import sys

from .core import (AssetError, asset_target, cache_lock, download_file, google_token,
                   import_file, load_manifest, select_assets, verify_file)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Verify and sync pinned Google Drive resources into .local-assets/.")
    parser.add_argument("--manifest", type=Path, default=Path("assets/manifest.yaml"))
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("list", "verify", "sync", "import"):
        command = commands.add_parser(name)
        command.add_argument("--id", action="append", default=[])
        command.add_argument("--character")
        command.add_argument("--episode")
        command.add_argument("--scene")
        if name == "sync":
            command.add_argument("--credentials", type=Path, default=os.environ.get("UKI_GOOGLE_CREDENTIALS"))
        if name == "import":
            command.add_argument("--file", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        repo = args.manifest.resolve().parent.parent
        assets = select_assets(load_manifest(args.manifest), ids=args.id,
                               character=args.character, episode=args.episode, scene=args.scene)
        if args.command == "import" and (len(assets) != 1 or len(args.id) != 1):
            raise AssetError("import requires exactly one --id.")
        if args.command == "list":
            for asset in assets:
                print(f"{asset.id}\t{asset.version}\t{asset.status}\t.local-assets/{asset.path}")
            return 0
        token = None
        def token_provider():
            nonlocal token
            if token is None:
                token = google_token(args.credentials)
            return token
        with cache_lock(repo):
            for asset in assets:
                if args.command == "verify":
                    verify_file(asset, asset_target(repo, asset))
                    result = "verified"
                elif args.command == "import":
                    result = import_file(asset, repo, args.file)
                else:
                    result = download_file(asset, repo, token_provider)
                print(f"{asset.id}: {result} ({asset.version})")
        return 0
    except AssetError as exc:
        print(f"Asset Sync: {exc}", file=sys.stderr)
        return 1
    except OSError:
        print("Asset Sync: local file access failed; check permissions and free space.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
