"""Install only the two approved presets and their tips, without replacing files."""

import argparse
import hashlib
import os
from pathlib import Path
import sys
import zipfile

from pipeline.assets.core import AssetError, asset_target, load_manifest, verify_file


PRESETS = {
    "krita.brush.bristles-5-flat": "f)_Bristles-5_Flat.kpp",
    "krita.brush.dry-bristles": "g)_Dry_Bristles.kpp",
}
TIPS = {"rake_flat.png", "scratches_rough.gih", "abominable_snowman.png"}


def collect_resources(repo, assets):
    resources = {}
    by_id = {a.id: a for a in assets}
    for asset_id, preset in PRESETS.items():
        if asset_id not in by_id:
            raise AssetError(f"Missing brush archive: {asset_id}.")
        asset = by_id[asset_id]
        archive = asset_target(repo, asset)
        verify_file(asset, archive)
        with zipfile.ZipFile(archive) as bundle:
            if len(bundle.namelist()) != len(set(bundle.namelist())):
                raise AssetError("Duplicate ZIP member.")
            if bundle.testzip() is not None:
                raise AssetError("Brush archive CRC failed.")
            for line in bundle.read("SHA256SUMS").decode("utf-8").splitlines():
                expected, name = line.split("  ", 1)
                if hashlib.sha256(bundle.read(name)).hexdigest() != expected:
                    raise AssetError("Brush archive SHA256SUMS failed.")
            presets = [n for n in bundle.namelist() if n.startswith("resources/paintoppresets/")]
            if presets != ["resources/paintoppresets/" + preset]:
                raise AssetError("Archive contains unexpected presets.")
            for name in bundle.namelist():
                relative = name.removeprefix("resources/")
                if relative == "paintoppresets/" + preset or relative in {"brushes/" + tip for tip in TIPS}:
                    content = bundle.read(name)
                    if relative in resources and resources[relative] != content:
                        raise AssetError("Brush archives disagree about a shared tip.")
                    resources[relative] = content
    expected = {"paintoppresets/" + preset for preset in PRESETS.values()} | {"brushes/" + tip for tip in TIPS}
    if set(resources) != expected:
        raise AssetError("Missing approved brush resources.")
    return resources


def install(resources, root, *, apply=False):
    root = Path(root).absolute()
    # Inspect every target before writing anything; different local resources survive.
    for name, data in resources.items():
        target = root / name
        if any(p.is_symlink() for p in (target, *target.parents)):
            raise AssetError("Symlinks in Krita resource paths are not supported.")
        if target.exists() and (not target.is_file() or target.read_bytes() != data):
            raise AssetError(f"Local resource differs; preserved: {target.name}.")
    for name, data in resources.items():
        target = root / name
        if target.exists():
            print(f"verified: {name}")
        elif apply:
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as stream:
                stream.write(data)
            print(f"installed: {name}")
        else:
            print(f"would install: {name}")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("assets/manifest.yaml"))
    data_home = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    parser.add_argument("--resource-dir", type=Path, default=data_home / "krita")
    parser.add_argument("--install", action="store_true", help="Write resources; default is inspection only.")
    args = parser.parse_args(argv)
    try:
        resources = collect_resources(args.manifest.resolve().parent.parent, load_manifest(args.manifest))
        install(resources, args.resource_dir, apply=args.install)
        return 0
    except (AssetError, OSError, zipfile.BadZipFile, KeyError, ValueError) as exc:
        print(f"Krita brushes: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
