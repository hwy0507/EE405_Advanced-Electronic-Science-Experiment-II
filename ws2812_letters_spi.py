#!/usr/bin/env python3
"""
WS2812 8x8 letter display via SPI MOSI (Orange Pi Zero 3 PH7)

Hardware assumptions:
- LED panel: WS2812/WS2812B, 8x8 = 64 pixels, single data-in wire
- Data wire (DIN) connected to PH7 (SPI1_MOSI)
- External 5V power for LED panel, and GND shared with Orange Pi

This script uses SPI bit encoding (0->100, 1->110) to generate WS2812 timing.
It does NOT use Linux PWM peripheral directly.
"""

from __future__ import annotations

import argparse
import re
import sys
import time
from typing import Dict, Iterable, List, Sequence, Tuple


FONT_5x7: Dict[str, Sequence[str]] = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01110"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "10001", "11001", "10101", "10011", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "10101", "01010"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "00110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    "?": ["01110", "10001", "00010", "00100", "00100", "00000", "00100"],
}

COLOR_MAP = {
    "red": (255, 0, 0),
    "green": (0, 255, 0),
    "blue": (0, 0, 255),
    "yellow": (255, 255, 0),
    "cyan": (0, 255, 255),
    "magenta": (255, 0, 255),
    "white": (255, 255, 255),
    "orange": (255, 120, 0),
    "purple": (180, 0, 255),
}


def parse_spidev_path(path: str) -> Tuple[int, int]:
    m = re.fullmatch(r"/dev/spidev(\d+)\.(\d+)", path)
    if not m:
        raise ValueError(f"Invalid spidev path: {path}")
    return int(m.group(1)), int(m.group(2))


def build_encode_lut() -> List[bytes]:
    """Encode one WS2812 byte into 3 SPI bytes with 3-bit symbols.

    Symbol mapping:
    - WS bit 0 -> SPI bits 100
    - WS bit 1 -> SPI bits 110
    """
    lut: List[bytes] = []
    for b in range(256):
        v = 0
        for i in range(8):
            bit = (b >> (7 - i)) & 1
            sym = 0b110 if bit else 0b100
            v = (v << 3) | sym
        lut.append(bytes(((v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF)))
    return lut


class WS2812SPI:
    def __init__(self, spidev_path: str, num_leds: int, speed_hz: int = 2_400_000):
        try:
            import spidev  # type: ignore
        except Exception as exc:
            raise RuntimeError(
                "缺少 spidev。请安装：sudo apt install python3-spidev 或 python3 -m pip install spidev"
            ) from exc

        bus, dev = parse_spidev_path(spidev_path)
        self.spi = spidev.SpiDev()
        self.spi.open(bus, dev)
        self.spi.mode = 0
        self.spi.max_speed_hz = speed_hz
        self.num_leds = num_leds
        self.lut = build_encode_lut()

    def close(self):
        try:
            self.spi.close()
        except Exception:
            pass

    def show(self, pixels: Sequence[Tuple[int, int, int]]):
        if len(pixels) != self.num_leds:
            raise ValueError(f"pixels length {len(pixels)} != num_leds {self.num_leds}")

        payload = bytearray()
        # WS2812 expects GRB order
        for r, g, b in pixels:
            payload += self.lut[g & 0xFF]
            payload += self.lut[r & 0xFF]
            payload += self.lut[b & 0xFF]

        # Add low-time reset tail (all zeros)
        payload += b"\x00" * 128
        self.spi.writebytes2(payload)
        time.sleep(0.00035)  # >= 300us latch gap for better compatibility


def parse_color(value: str) -> Tuple[int, int, int]:
    v = value.strip().lower()
    if v in COLOR_MAP:
        return COLOR_MAP[v]
    if v.startswith("#") and len(v) == 7:
        return (int(v[1:3], 16), int(v[3:5], 16), int(v[5:7], 16))
    raise ValueError(f"Unsupported color: {value}")


def apply_brightness(rgb: Tuple[int, int, int], brightness: float) -> Tuple[int, int, int]:
    b = max(0.0, min(1.0, brightness))
    return tuple(int(round(c * b)) for c in rgb)  # type: ignore


def transform_xy(
    x: int,
    y: int,
    cols: int,
    rows: int,
    rotate: int = 0,
    flip_x: bool = False,
    flip_y: bool = False,
) -> Tuple[int, int]:
    """Transform logical coordinate before wiring map."""
    if flip_x:
        x = cols - 1 - x
    if flip_y:
        y = rows - 1 - y

    r = rotate % 360
    if r == 0:
        return x, y
    if r == 90:
        return rows - 1 - y, x
    if r == 180:
        return cols - 1 - x, rows - 1 - y
    if r == 270:
        return y, cols - 1 - x
    raise ValueError("rotate must be one of 0, 90, 180, 270")


def pixel_index(
    x: int,
    y: int,
    cols: int,
    rows: int,
    layout: str,
) -> int:
    """Map physical matrix coordinate to LED index."""
    if layout == "row":
        return y * cols + x
    if layout == "row-serp":
        if y % 2 == 1:
            return y * cols + (cols - 1 - x)
        return y * cols + x
    if layout == "col":
        return x * rows + y
    if layout == "col-serp":
        if x % 2 == 1:
            return x * rows + (rows - 1 - y)
        return x * rows + y
    raise ValueError(f"unknown layout: {layout}")


def render_char_matrix(ch: str, cols: int = 8, rows: int = 8) -> List[List[int]]:
    glyph = FONT_5x7.get(ch.upper(), FONT_5x7["?"])
    gw, gh = 5, 7
    x_off = max(0, (cols - gw) // 2)
    y_off = max(0, (rows - gh) // 2)

    mat = [[0 for _ in range(cols)] for _ in range(rows)]
    for gy in range(min(gh, rows - y_off)):
        row_bits = glyph[gy]
        for gx in range(min(gw, cols - x_off)):
            if row_bits[gx] == "1":
                mat[y_off + gy][x_off + gx] = 1
    return mat


def matrix_to_pixels(
    mat: Sequence[Sequence[int]],
    on_rgb: Tuple[int, int, int],
    off_rgb: Tuple[int, int, int],
    layout: str,
    rotate: int,
    flip_x: bool,
    flip_y: bool,
) -> List[Tuple[int, int, int]]:
    rows = len(mat)
    cols = len(mat[0]) if rows else 0
    out = [off_rgb] * (rows * cols)
    for y in range(rows):
        for x in range(cols):
            tx, ty = transform_xy(x, y, cols, rows, rotate=rotate, flip_x=flip_x, flip_y=flip_y)
            idx = pixel_index(tx, ty, cols, rows, layout=layout)
            out[idx] = on_rgb if mat[y][x] else off_rgb
    return out


def clear_strip(dev: WS2812SPI):
    dev.show([(0, 0, 0)] * dev.num_leds)


def run_text(
    dev: WS2812SPI,
    text: str,
    color: Tuple[int, int, int],
    bg: Tuple[int, int, int],
    interval: float,
    layout: str,
    rotate: int,
    flip_x: bool,
    flip_y: bool,
):
    for ch in text:
        mat = render_char_matrix(ch, cols=8, rows=8)
        pixels = matrix_to_pixels(
            mat, color, bg, layout=layout, rotate=rotate, flip_x=flip_x, flip_y=flip_y
        )
        dev.show(pixels)
        time.sleep(interval)


def run_demo(
    dev: WS2812SPI,
    color: Tuple[int, int, int],
    layout: str,
    rotate: int,
    flip_x: bool,
    flip_y: bool,
):
    for ch in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
        mat = render_char_matrix(ch)
        pixels = matrix_to_pixels(
            mat, color, (0, 0, 0), layout=layout, rotate=rotate, flip_x=flip_x, flip_y=flip_y
        )
        dev.show(pixels)
        time.sleep(0.18)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="WS2812 8x8 letters via SPI (Orange Pi PH7/MOSI)")
    ap.add_argument("--spi", default="/dev/spidev1.0", help="spidev node, e.g. /dev/spidev1.0")
    ap.add_argument("--freq", type=int, default=2_400_000, help="SPI frequency, typical 2.4MHz or 3.0MHz")
    ap.add_argument("--text", default="A", help="Text to display, e.g. HELLO")
    ap.add_argument("--color", default="blue", help="Color name or #RRGGBB")
    ap.add_argument("--bg", default="#000000", help="Background color")
    ap.add_argument("--brightness", type=float, default=0.2, help="0.0~1.0")
    ap.add_argument("--interval", type=float, default=0.8, help="seconds per character")
    ap.add_argument(
        "--layout",
        default="row-serp",
        choices=["row-serp", "row", "col-serp", "col"],
        help="physical wiring layout",
    )
    ap.add_argument("--rotate", type=int, default=0, choices=[0, 90, 180, 270], help="logical rotate")
    ap.add_argument("--flip-x", action="store_true", help="mirror X")
    ap.add_argument("--flip-y", action="store_true", help="mirror Y")
    ap.add_argument("--demo", action="store_true", help="show A-Z0-9 demo quickly")
    ap.add_argument("--loop", action="store_true", help="loop text/demo until Ctrl+C")
    ap.add_argument("--clear-at-end", action="store_true", help="turn off LEDs before exit")
    return ap.parse_args()


def main() -> int:
    args = parse_args()

    on = apply_brightness(parse_color(args.color), args.brightness)
    off = apply_brightness(parse_color(args.bg), args.brightness)

    print("[INFO] Starting WS2812 SPI driver")
    print(
        f"[INFO] SPI={args.spi} freq={args.freq}Hz "
        f"layout={args.layout} rotate={args.rotate} flip_x={args.flip_x} flip_y={args.flip_y}"
    )
    print(f"[INFO] text={args.text!r} color={on} bg={off}")

    dev = WS2812SPI(args.spi, num_leds=64, speed_hz=args.freq)
    try:
        while True:
            if args.demo:
                run_demo(
                    dev,
                    on,
                    layout=args.layout,
                    rotate=args.rotate,
                    flip_x=args.flip_x,
                    flip_y=args.flip_y,
                )
            else:
                run_text(
                    dev,
                    args.text,
                    on,
                    off,
                    args.interval,
                    layout=args.layout,
                    rotate=args.rotate,
                    flip_x=args.flip_x,
                    flip_y=args.flip_y,
                )
            if not args.loop:
                break
    except KeyboardInterrupt:
        pass
    finally:
        if args.clear_at_end:
            clear_strip(dev)
        dev.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
