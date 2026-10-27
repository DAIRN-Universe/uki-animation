"""Export accepted Uki v7 views inside Krita 6 without changing the document.

From Krita's Python console/MCP: export(krita.activeDocument(), repository_path).
PNG files and the local QA report remain under .local-assets/.
"""

import hashlib
import json
from pathlib import Path
import sys
import zipfile


SOURCE_SHA256 = "91e1ad07a4e980f903f4af432bdf157332be799b88f028c3597ba262db1c5340"
VIEWS = (
    ("front", "01 — Анфас", "FRONT"),
    ("three_quarter", "02 — Три четверти", "THREE-QUARTER"),
    ("profile", "03 — Профиль", "PROFILE"),
    ("back", "04 — Сзади", "BACK"),
    ("profile_head_front", "05 — Тело в профиль · голова к зрителю на 90°", "ADDITIONAL"),
)


def export(document, repository):
    from krita import Krita
    from PyQt6.QtCore import QRect, Qt
    from PyQt6.QtGui import QColor, QColorSpace, QFont, QImage, QPainter

    if not Krita.instance().version().startswith("6.") or sys.byteorder != "little":
        raise RuntimeError("Requires Krita 6 and little-endian RGBA/U8 pixel layout.")
    repository = Path(repository).resolve()
    source = repository / ".local-assets/characters/uki/poses/uki_five_views_brush_cleanup_v7.kra"
    if (Path(document.fileName()).resolve() != source or document.modified()
            or hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256):
        raise RuntimeError("Open the unchanged, hash-verified v7 source first.")
    if (document.width(), document.height(), document.colorModel(), document.colorDepth()) != (440, 560, "RGBA", "U8"):
        raise RuntimeError("Unexpected source canvas or colour model.")
    groups = document.rootNode().childNodes()
    if len(groups) != 5 or {g.name() for g in groups} != {name for _, name, _ in VIEWS}:
        raise RuntimeError("Expected exactly the five accepted v7 groups.")
    if any(g.type() != "grouplayer" for g in groups):
        raise RuntimeError("Expected five group layers.")
    by_name = {g.name(): g for g in groups}
    visibility = [(g.uniqueId().toString(), g.visible()) for g in groups]
    output = repository / ".local-assets/characters/uki/references/views_v7"
    if output.exists():
        raise RuntimeError("Output already exists; preserve it and choose a new version before re-exporting.")
    with zipfile.ZipFile(source) as archive:
        icc_files = [n for n in archive.namelist() if n.endswith("/annotations/icc")]
        if len(icc_files) != 1:
            raise RuntimeError("Expected one embedded document ICC profile.")
        icc = archive.read(icc_files[0])
    colour_space = QColorSpace.fromIccProfile(icc)
    if not colour_space.isValid():
        raise RuntimeError("Source ICC profile is invalid.")
    document.waitForDone()
    output.mkdir(parents=True)
    width, height, caption_height = 440, 560, 56
    raws, records = [], []

    def save(image, name, **metadata):
        image.setColorSpace(colour_space)
        dots_per_metre = round(document.resolution() / 0.0254)
        image.setDotsPerMeterX(dots_per_metre)
        image.setDotsPerMeterY(dots_per_metre)
        image.setText("Source", "uki.poses.v7; " + SOURCE_SHA256)
        image.setText("Generator", "Krita " + Krita.instance().version())
        path = output / name
        if not image.save(str(path), "PNG"):
            raise RuntimeError("PNG export failed: " + name)
        records.append(dict(file=name, size_bytes=path.stat().st_size,
                            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            width=image.width(), height=image.height(), **metadata))

    for key, group_name, _ in VIEWS:
        raw = bytes(by_name[group_name].projectionPixelData(0, 0, width, height))
        if len(raw) != width * height * 4:
            raise RuntimeError("Unexpected projection byte count.")
        image = QImage(raw, width, height, width * 4, QImage.Format.Format_ARGB32).copy()
        alpha = raw[3::4]
        occupied = [i for i, a in enumerate(alpha) if a]
        if not occupied or 0 not in alpha:
            raise RuntimeError("Expected a non-empty image with transparent background.")
        xs, ys = [i % width for i in occupied], [i // width for i in occupied]
        bbox = [min(xs), min(ys), max(xs) + 1, max(ys) + 1]
        save(image, "uki_" + key + "_v7.png", group=group_name,
             role="primary" if len(raws) < 4 else "additional", alpha_bbox=bbox,
             projection_bgra_sha256=hashlib.sha256(raw).hexdigest())
        raws.append(raw)

    # Labels occupy a separate band. Original projection bytes are copied at
    # native size: no resampling, crop, translation inside a source canvas or repaint.
    sheet_width = width * 4
    header = QImage(sheet_width, caption_height, QImage.Format.Format_ARGB32)
    header.fill(QColor("#f2f4f7"))
    painter = QPainter(header)
    painter.setPen(QColor("#243044"))
    font = QFont("DejaVu Sans")
    font.setPixelSize(20)
    painter.setFont(font)
    for index, (_, _, label) in enumerate(VIEWS[:4]):
        painter.drawText(QRect(index * width, 0, width, caption_height), Qt.AlignmentFlag.AlignCenter, label)
    painter.end()
    pointer = header.constBits()
    pointer.setsize(header.sizeInBytes())
    sheet_raw = bytearray(bytes(pointer))
    for y in range(height):
        for raw in raws[:4]:
            sheet_raw.extend(raw[y * width * 4:(y + 1) * width * 4])
    sheet = QImage(bytes(sheet_raw), sheet_width, height + caption_height,
                   sheet_width * 4, QImage.Format.Format_ARGB32).copy()
    save(sheet, "uki_reference_sheet_v7.png", role="reference_sheet",
         order=[key for key, _, _ in VIEWS[:4]], caption_height=caption_height)
    if document.modified() or visibility != [(g.uniqueId().toString(), g.visible()) for g in groups]:
        raise RuntimeError("Source document state changed unexpectedly.")
    if hashlib.sha256(source.read_bytes()).hexdigest() != SOURCE_SHA256:
        raise RuntimeError("Source file changed unexpectedly.")
    report = dict(source_id="uki.poses.v7", source_sha256=SOURCE_SHA256,
                  krita_version=Krita.instance().version(), profile=document.colorProfile(),
                  icc_sha256=hashlib.sha256(icc).hexdigest(), source_modified=False,
                  source_visibility_unchanged=True, exports=records)
    (output / "export-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report
