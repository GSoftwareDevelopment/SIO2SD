#!/usr/bin/env python3
"""Generate the SIO2SD GUI icon assets without external dependencies."""

import os
import struct
import zlib


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSET_DIR = os.path.join(ROOT, 'assets')
PNG_PATH = os.path.join(ASSET_DIR, 'sio2sd_gui_icon.png')
ICO_PATH = os.path.join(ASSET_DIR, 'sio2sd_gui_icon.ico')


def _blend(dst, src):
    sr, sg, sb, sa = src
    if sa <= 0:
        return dst
    if sa >= 255:
        return src
    dr, dg, db, da = dst
    a = sa / 255.0
    ia = 1.0 - a
    out_a = sa + da * ia
    if out_a <= 0:
        return (0, 0, 0, 0)
    return (
        int(sr * a + dr * ia + 0.5),
        int(sg * a + dg * ia + 0.5),
        int(sb * a + db * ia + 0.5),
        int(out_a + 0.5),
    )


def _put(img, size, x, y, color):
    if 0 <= x < size and 0 <= y < size:
        img[y][x] = _blend(img[y][x], color)


def _round_rect(img, size, x0, y0, x1, y1, radius, color):
    r2 = radius * radius
    for y in range(y0, y1):
        for x in range(x0, x1):
            cx = x0 + radius if x < x0 + radius else x1 - radius - 1
            cy = y0 + radius if y < y0 + radius else y1 - radius - 1
            if (x0 + radius <= x < x1 - radius or
                    y0 + radius <= y < y1 - radius or
                    (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r2):
                _put(img, size, x, y, color)


def _rect(img, size, x0, y0, x1, y1, color):
    for y in range(y0, y1):
        for x in range(x0, x1):
            _put(img, size, x, y, color)


def _circle(img, size, cx, cy, radius, color):
    r2 = radius * radius
    for y in range(cy - radius, cy + radius + 1):
        for x in range(cx - radius, cx + radius + 1):
            if (x - cx) * (x - cx) + (y - cy) * (y - cy) <= r2:
                _put(img, size, x, y, color)


def _line(img, size, x0, y0, x1, y1, width, color):
    dx = x1 - x0
    dy = y1 - y0
    steps = max(abs(dx), abs(dy), 1)
    for i in range(steps + 1):
        x = int(x0 + dx * i / steps + 0.5)
        y = int(y0 + dy * i / steps + 0.5)
        _circle(img, size, x, y, width // 2, color)


PIXEL_FONT = {
    '2': ('11110', '00001', '00001', '11110', '10000', '10000', '11111'),
    'D': ('11110', '10001', '10001', '10001', '10001', '10001', '11110'),
    'I': ('11111', '00100', '00100', '00100', '00100', '00100', '11111'),
    'O': ('01110', '10001', '10001', '10001', '10001', '10001', '01110'),
    'S': ('01111', '10000', '10000', '01110', '00001', '00001', '11110'),
}


def _draw_text(img, size, text, x, y, scale, color, spacing=1):
    cursor = x
    for char in text:
        if char == ' ':
            cursor += 4 * scale
            continue
        pattern = PIXEL_FONT[char]
        for row, bits in enumerate(pattern):
            for col, bit in enumerate(bits):
                if bit == '1':
                    _rect(img, size,
                          cursor + col * scale, y + row * scale,
                          cursor + (col + 1) * scale,
                          y + (row + 1) * scale,
                          color)
        cursor += (5 + spacing) * scale


def _draw_icon(size):
    img = [[(0, 0, 0, 0) for _ in range(size)] for _ in range(size)]
    scale = size / 256.0

    def s(value):
        return int(value * scale + 0.5)

    _round_rect(img, size, s(18), s(18), s(238), s(238), s(44),
                (14, 31, 42, 255))
    _round_rect(img, size, s(28), s(28), s(228), s(228), s(34),
                (37, 87, 94, 255))
    _round_rect(img, size, s(38), s(38), s(218), s(218), s(26),
                (11, 27, 34, 255))

    _draw_text(img, size, 'SIO', s(48), s(48), s(8), (248, 244, 221, 255),
               spacing=1)

    # SIO cable, visually spelling the bridge to SD.
    _line(img, size, s(57), s(158), s(95), s(183), s(13),
          (255, 195, 63, 255))
    _line(img, size, s(95), s(183), s(139), s(183), s(13),
          (255, 195, 63, 255))
    _line(img, size, s(139), s(183), s(171), s(151), s(13),
          (255, 195, 63, 255))
    _circle(img, size, s(54), s(156), s(18), (255, 224, 94, 255))
    _circle(img, size, s(54), s(156), s(7), (11, 27, 34, 255))

    # SD card body.
    _round_rect(img, size, s(150), s(82), s(205), s(183), s(8),
                (103, 236, 198, 255))
    _rect(img, size, s(167), s(82), s(190), s(106), (11, 27, 34, 255))
    _rect(img, size, s(158), s(120), s(197), s(130), (39, 120, 119, 255))
    _rect(img, size, s(158), s(139), s(197), s(149), (39, 120, 119, 255))
    _draw_text(img, size, 'SD', s(158), s(153), s(4), (11, 27, 34, 255),
               spacing=1)

    _draw_text(img, size, '2', s(104), s(126), s(7), (255, 195, 63, 255),
               spacing=1)

    return img


def _downsample(img, src_size, dst_size):
    if src_size == dst_size:
        return img
    ratio = src_size // dst_size
    out = []
    for y in range(dst_size):
        row = []
        for x in range(dst_size):
            sums = [0, 0, 0, 0]
            for yy in range(y * ratio, (y + 1) * ratio):
                for xx in range(x * ratio, (x + 1) * ratio):
                    px = img[yy][xx]
                    for i in range(4):
                        sums[i] += px[i]
            count = ratio * ratio
            row.append(tuple(int(v / count + 0.5) for v in sums))
        out.append(row)
    return out


def _png_bytes(img, size):
    raw = bytearray()
    for row in img:
        raw.append(0)
        for r, g, b, a in row:
            raw.extend((r, g, b, a))
    def chunk(name, payload):
        return (
            struct.pack('>I', len(payload)) + name + payload +
            struct.pack('>I', zlib.crc32(name + payload) & 0xFFFFFFFF)
        )
    return (
        b'\x89PNG\r\n\x1a\n' +
        chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0)) +
        chunk(b'IDAT', zlib.compress(bytes(raw), 9)) +
        chunk(b'IEND', b'')
    )


def _ico_bytes(master):
    sizes = [16, 24, 32, 48, 64, 128, 256]
    entries = []
    images = []
    for size in sizes:
        img = _downsample(master, 1024, size)
        data = _png_bytes(img, size)
        entries.append((size, len(data)))
        images.append(data)
    header = bytearray(struct.pack('<HHH', 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for size, length in entries:
        header.extend(struct.pack(
            '<BBBBHHII',
            0 if size == 256 else size,
            0 if size == 256 else size,
            0, 0, 1, 32, length, offset))
        offset += length
    return bytes(header) + b''.join(images)


def main():
    os.makedirs(ASSET_DIR, exist_ok=True)
    master = _draw_icon(1024)
    icon_256 = _downsample(master, 1024, 256)
    with open(PNG_PATH, 'wb') as f:
        f.write(_png_bytes(icon_256, 256))
    with open(ICO_PATH, 'wb') as f:
        f.write(_ico_bytes(master))
    print(PNG_PATH)
    print(ICO_PATH)


if __name__ == '__main__':
    main()
