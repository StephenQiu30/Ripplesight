from __future__ import annotations

import struct


def validate_screenshot(data: bytes, mime: str) -> tuple[int, int]:
    if not 1 <= len(data) <= 8388608:
        raise ValueError("screenshot must be at most 8 MiB")
    if mime == "image/png":
        if (
            len(data) < 45
            or not data.startswith(b"\x89PNG\r\n\x1a\n")
            or data[12:16] != b"IHDR"
            or data[-8:-4] != b"IEND"
        ):
            raise ValueError("invalid PNG screenshot")
        width, height = struct.unpack(">II", data[16:24])
    elif mime == "image/gif":
        if len(data) < 14 or data[:6] not in {b"GIF87a", b"GIF89a"} or data[-1:] != b";":
            raise ValueError("invalid GIF screenshot")
        width, height = struct.unpack("<HH", data[6:10])
    elif mime == "image/webp":
        if (
            len(data) < 30
            or data[:4] != b"RIFF"
            or data[8:12] != b"WEBP"
            or int.from_bytes(data[4:8], "little") + 8 != len(data)
        ):
            raise ValueError("invalid WebP screenshot")
        if data[12:16] == b"VP8X":
            width = int.from_bytes(data[24:27], "little") + 1
            height = int.from_bytes(data[27:30], "little") + 1
        elif data[12:16] == b"VP8L" and data[20] == 0x2F:
            bits = int.from_bytes(data[21:25], "little")
            width = (bits & 0x3FFF) + 1
            height = ((bits >> 14) & 0x3FFF) + 1
        elif data[12:16] == b"VP8 " and data[23:26] == b"\x9d\x01\x2a":
            width = int.from_bytes(data[26:28], "little") & 0x3FFF
            height = int.from_bytes(data[28:30], "little") & 0x3FFF
        else:
            raise ValueError("unsupported WebP image chunk")
    elif mime == "image/jpeg":
        if data[:2] != b"\xff\xd8" or data[-2:] != b"\xff\xd9":
            raise ValueError("invalid JPEG screenshot")
        offset = 2
        width = height = 0
        while offset + 4 <= len(data):
            if data[offset] != 0xFF:
                break
            marker = data[offset + 1]
            offset += 2
            if marker in {0xD8, 0xD9}:
                continue
            size = int.from_bytes(data[offset : offset + 2], "big")
            if size < 2 or offset + size > len(data):
                break
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                if size < 8:
                    break
                height, width = struct.unpack(">HH", data[offset + 3 : offset + 7])
                break
            offset += size
    else:
        raise ValueError("unsupported screenshot MIME")
    if not 1 <= width <= 20000 or not 1 <= height <= 20000 or width * height > 40000000:
        raise ValueError("screenshot dimensions exceed limit")
    return width, height
