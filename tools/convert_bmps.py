#!/usr/bin/env python3
"""Convert animation strips (BMP/PNG) into small palette BMPs.

Frames are stacked vertically (e.g. 64x2336 = 73 frames of 64x32), as expected
by clock/parse.py. Output is a 4-bit (<=16 colors) or 8-bit (<=256 colors)
indexed BMP, which displayio.OnDiskBitmap can stream straight from flash.

    pip install Pillow
    python tools/convert_bmps.py bmps/*.bmp                 # in place, 16 colors
    python tools/convert_bmps.py -c 32 -o out/ bmps/fireworks.bmp
    python tools/convert_bmps.py --dry-run bmps/*.bmp
"""

import argparse
import os
import struct
import sys

from PIL import Image

FRAME_HEIGHT = 32


def median_cut(counts, colors):
    """Weighted median cut. Pixel counts are square-rooted so rare bright
    colors (sparks on a black background) still earn palette entries."""
    boxes = [[(c, n**0.5) for c, n in counts.items()]]
    while len(boxes) < colors:
        splittable = [b for b in boxes if len(b) > 1]
        if not splittable:
            break

        def spread(box):
            return max(max(c[i] for c, _ in box) - min(c[i] for c, _ in box) for i in range(3))

        box = max(splittable, key=spread)
        boxes.remove(box)
        axis = max(
            range(3),
            key=lambda i: max(c[i] for c, _ in box) - min(c[i] for c, _ in box),
        )
        box.sort(key=lambda cw: cw[0][axis])
        half = sum(w for _, w in box) / 2
        acc = 0
        cut = 1
        for i, (_, w) in enumerate(box):
            acc += w
            if acc >= half:
                cut = min(max(i + 1, 1), len(box) - 1)
                break
        boxes += [box[:cut], box[cut:]]

    palette = []
    for box in boxes:
        total = sum(w for _, w in box)
        palette.append(
            tuple(round(sum(c[i] * w for c, w in box) / total) for i in range(3))
        )
    return sorted(palette)


def quantize(img, colors, black_threshold):
    """Return (index image of mode P, palette as list of (r, g, b))."""
    counts = {}
    snap = {}
    for n, c in img.getcolors(1 << 24):
        # Near-black is invisible on an LED matrix; snap it to true black
        key = (0, 0, 0) if max(c) <= black_threshold else c
        snap[c] = key
        counts[key] = counts.get(key, 0) + n
    if len(counts) <= colors:
        # Few enough colors already: keep them exactly
        palette = sorted(counts)
    elif (0, 0, 0) in counts:
        # Keep true black exact: on an LED matrix it means "off", and tinted
        # black backgrounds show up as a visible glowing rectangle
        rest = {c: n for c, n in counts.items() if c != (0, 0, 0)}
        palette = sorted(median_cut(rest, colors - 1) + [(0, 0, 0)])
    else:
        palette = median_cut(counts, colors)

    lookup = {}
    for c, key in snap.items():
        lookup[c] = min(
            range(len(palette)),
            key=lambda i: sum((a - b) ** 2 for a, b in zip(palette[i], key)),
        )
    out = Image.new("P", img.size)
    out.putdata([lookup[p] for p in img.getdata()])
    return out, palette


def write_bmp(path, indexed, palette):
    width, height = indexed.size
    bpp = 4 if len(palette) <= 16 else 8
    row_size = ((width * bpp + 31) // 32) * 4
    pixels = indexed.load()

    rows = bytearray()
    for y in range(height - 1, -1, -1):  # BMP rows are stored bottom-up
        row = bytearray(row_size)
        if bpp == 8:
            for x in range(width):
                row[x] = pixels[x, y]
        else:
            for x in range(width):
                row[x // 2] |= pixels[x, y] << (4 if x % 2 == 0 else 0)
        rows += row

    palette_size = len(palette) * 4
    offset = 14 + 40 + palette_size
    header = b"BM" + struct.pack("<IHHI", offset + len(rows), 0, 0, offset)
    info = struct.pack(
        "<IiiHHIIiiII",
        40,
        width,
        height,
        1,
        bpp,
        0,
        len(rows),
        2835,
        2835,
        len(palette),
        len(palette),
    )
    table = b"".join(struct.pack("<BBBB", b, g, r, 0) for r, g, b in palette)
    with open(path, "wb") as f:
        f.write(header + info + table + rows)
    return bpp


def convert(src, dst, colors, black_threshold, dry_run):
    img = Image.open(src).convert("RGB")
    width, height = img.size
    if height % FRAME_HEIGHT:
        print(f"warning: {src}: height {height} is not a multiple of {FRAME_HEIGHT}")
    indexed, palette = quantize(img, colors, black_threshold)
    if dry_run:
        print(f"{src}: {len(palette)} colors, {height // FRAME_HEIGHT} frames")
        return
    before = os.path.getsize(src)
    bpp = write_bmp(dst, indexed, palette)
    after = os.path.getsize(dst)
    print(
        f"{src}: {before:>7} -> {after:>7} bytes "
        f"({bpp}-bit, {len(palette)} colors, {height // FRAME_HEIGHT} frames)"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("files", nargs="+")
    parser.add_argument(
        "-c", "--colors", type=int, default=16, help="max colors, 2-256 (default 16)"
    )
    parser.add_argument(
        "-b",
        "--black-threshold",
        type=int,
        default=8,
        help="snap colors with all channels <= this to black (default 8)",
    )
    parser.add_argument("-o", "--out-dir", help="write here instead of in place")
    parser.add_argument("-n", "--dry-run", action="store_true")
    args = parser.parse_args()

    if not 2 <= args.colors <= 256:
        parser.error("--colors must be between 2 and 256")
    if args.out_dir:
        os.makedirs(args.out_dir, exist_ok=True)

    for src in args.files:
        stem = os.path.splitext(os.path.basename(src))[0] + ".bmp"
        if args.out_dir:
            dst = os.path.join(args.out_dir, stem)
        else:
            dst = os.path.splitext(src)[0] + ".bmp"
        convert(src, dst, args.colors, args.black_threshold, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())
