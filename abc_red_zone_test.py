#!/usr/bin/env python3
"""
ABC fan-zone tracker (standalone test)

功能：
- 追踪红色方块（最大红色连通域）
- 把画面中的判定区域定义成 3 个扇形（A/B/C），不需要覆盖全画面
- B 扇形的中轴由“标定时红色方块方向”确定，左右分别是 A/C
- 标定时圆心自动放在“红色方块正下方”
- 按键输出当前红色方块处于哪个扇形

按键：
- c: 用当前红色方块位置重新标定 B 扇形中轴
- p: 输出当前区域
- q: 退出
"""

from __future__ import annotations

import argparse
import math
from typing import Optional, Tuple

import cv2
import numpy as np


def detect_red_center(
    frame_bgr: np.ndarray,
    min_area: float,
) -> Tuple[Optional[Tuple[int, int]], Optional[Tuple[int, int, int, int]], float, np.ndarray]:
    """Return (center, bbox, area, mask)."""
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)

    # Red wraps around hue=0, so use two intervals.
    lower1 = np.array([0, 100, 70], dtype=np.uint8)
    upper1 = np.array([10, 255, 255], dtype=np.uint8)
    lower2 = np.array([160, 100, 70], dtype=np.uint8)
    upper2 = np.array([179, 255, 255], dtype=np.uint8)

    mask1 = cv2.inRange(hsv, lower1, upper1)
    mask2 = cv2.inRange(hsv, lower2, upper2)
    mask = cv2.bitwise_or(mask1, mask2)

    kernel = np.ones((5, 5), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None, None, 0.0, mask

    c = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(c))
    if area < min_area:
        return None, None, area, mask

    x, y, w, h = cv2.boundingRect(c)
    m = cv2.moments(c)
    if m["m00"] == 0:
        return None, (x, y, x + w, y + h), area, mask

    cx = int(m["m10"] / m["m00"])
    cy = int(m["m01"] / m["m00"])
    return (cx, cy), (x, y, x + w, y + h), area, mask


def normalize_deg(a: float) -> float:
    """Normalize angle to [-180, 180)."""
    x = (a + 180.0) % 360.0 - 180.0
    return x


def point_to_angle_deg(origin: Tuple[int, int], p: Tuple[int, int]) -> float:
    """Angle in degrees with image coordinates (+x right, +y down)."""
    ox, oy = origin
    px, py = p
    dx = px - ox
    dy = py - oy
    return math.degrees(math.atan2(dy, dx))


def classify_fan_zone(
    center: Tuple[int, int],
    origin: Tuple[int, int],
    axis_deg: float,
    b_half_deg: float,
    a_half_deg: float,
    c_half_deg: float,
    r_inner: float,
    r_outer: float,
) -> Optional[str]:
    """Classify center into A/B/C fan zones; return None if outside fan annulus."""
    ox, oy = origin
    cx, cy = center
    dx = cx - ox
    dy = cy - oy
    r = math.hypot(dx, dy)

    if r < r_inner or r > r_outer:
        return None

    ang = point_to_angle_deg(origin, center)
    rel = normalize_deg(ang - axis_deg)

    # B is around axis, A at left side, C at right side
    if abs(rel) <= b_half_deg:
        return "B"

    # Left side in image-angle convention (positive rel)
    a_center = b_half_deg + a_half_deg
    if abs(rel - a_center) <= a_half_deg:
        return "A"

    # Right side (negative rel)
    c_center = -(b_half_deg + c_half_deg)
    if abs(rel - c_center) <= c_half_deg:
        return "C"

    return None


def origin_below_center(center: Tuple[int, int], drop: float, frame_h: int) -> Tuple[int, int]:
    """Place fan origin below red block center with clamping."""
    cx, cy = center
    oy = int(round(cy + drop))
    oy = max(0, min(frame_h - 1, oy))
    return (cx, oy)


def draw_fan_overlay(
    frame: np.ndarray,
    center,
    bbox,
    zone: Optional[str],
    area: float,
    origin: Tuple[int, int],
    axis_deg: float,
    b_half_deg: float,
    a_half_deg: float,
    c_half_deg: float,
    r_inner: float,
    r_outer: float,
) -> np.ndarray:
    h, w = frame.shape[:2]
    ox, oy = origin

    # Draw ring boundaries
    cv2.circle(frame, origin, int(r_outer), (80, 120, 180), 1)
    cv2.circle(frame, origin, int(r_inner), (80, 120, 180), 1)

    # Draw sector center rays
    rays = [
        ("A", axis_deg + b_half_deg + a_half_deg, (255, 180, 80)),
        ("B", axis_deg, (80, 230, 255)),
        ("C", axis_deg - (b_half_deg + c_half_deg), (255, 180, 80)),
    ]

    for label, ang_deg, color in rays:
        rad = math.radians(ang_deg)
        x2 = int(ox + r_outer * math.cos(rad))
        y2 = int(oy + r_outer * math.sin(rad))
        cv2.line(frame, origin, (x2, y2), color, 1)

        tx = int(ox + (r_outer + 22) * math.cos(rad))
        ty = int(oy + (r_outer + 22) * math.sin(rad))
        tx = max(10, min(w - 30, tx))
        ty = max(20, min(h - 10, ty))
        cv2.putText(frame, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2)

    # Draw all sector boundary rays so A/C boundaries are visible.
    # Relative boundaries:
    # C outer | C/B shared | B/A shared | A outer
    #   -(b+2c)   -b            +b          +(b+2a)
    boundary_rel = [
        -(b_half_deg + 2.0 * c_half_deg),
        -b_half_deg,
        b_half_deg,
        (b_half_deg + 2.0 * a_half_deg),
    ]
    for rel in boundary_rel:
        ang = axis_deg + rel
        rad = math.radians(ang)
        x2 = int(ox + r_outer * math.cos(rad))
        y2 = int(oy + r_outer * math.sin(rad))
        # make boundaries thicker and brighter than center rays
        cv2.line(frame, origin, (x2, y2), (80, 255, 255), 2)

    # origin marker
    cv2.circle(frame, origin, 5, (180, 255, 180), -1)
    cv2.putText(frame, "origin", (ox + 8, oy - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (180, 255, 180), 1)

    if bbox is not None:
        x1, y1, x2, y2 = bbox
        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 220, 0), 2)
    if center is not None:
        cx, cy = center
        cv2.circle(frame, (cx, cy), 6, (0, 255, 255), -1)
        cv2.putText(
            frame,
            f"zone={zone if zone else 'OUT'} area={area:.0f}",
            (max(10, cx - 130), max(30, cy - 15)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 255),
            2,
        )
    else:
        cv2.putText(frame, "No red target", (15, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (40, 80, 255), 2)

    cv2.putText(
        frame,
        "c: calibrate B-axis  p: print zone  q: quit",
        (15, h - 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.65,
        (220, 220, 220),
        2,
    )

    return frame


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="ABC fan-zone red block tracker")
    ap.add_argument("--device", default="/dev/video1", help="camera device index or /dev/videoX")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--min-area", type=float, default=250.0, help="minimum contour area")
    ap.add_argument("--mjpg", action="store_true", help="request MJPG format")

    # fan parameters
    ap.add_argument("--origin-x", type=int, default=-1, help="fallback fan origin x (when not calibrated)")
    ap.add_argument("--origin-y", type=int, default=-1, help="fallback fan origin y (when not calibrated)")
    ap.add_argument("--origin-drop", type=float, default=130.0, help="origin is this many pixels below red center")
    ap.add_argument("--r-inner", type=float, default=60.0, help="inner radius of valid annulus")
    ap.add_argument("--r-outer", type=float, default=230.0, help="outer radius of valid annulus")

    ap.add_argument("--b-half", type=float, default=22.0, help="half angle of B sector (deg)")
    ap.add_argument("--a-half", type=float, default=22.0, help="half angle of A sector (deg)")
    ap.add_argument("--c-half", type=float, default=22.0, help="half angle of C sector (deg)")

    ap.add_argument("--auto-calib", action="store_true", help="auto set B-axis using first valid red center")
    return ap.parse_args()


def main() -> None:
    args = parse_args()

    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    if not cap.isOpened() and str(args.device).isdigit():
        cap = cv2.VideoCapture(int(args.device), cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera: {args.device}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, 30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    if args.mjpg:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

    print("[INFO] Ready. Keys: c=calibrate B axis, p=print zone, q=quit")

    axis_deg = 0.0
    axis_calibrated = False
    origin_ref: Optional[Tuple[int, int]] = None

    last_zone = None
    last_center = None
    last_area = 0.0
    origin = None

    while True:
        ok, frame = cap.read()
        if not ok:
            continue

        h, w = frame.shape[:2]
        fallback_ox = args.origin_x if args.origin_x >= 0 else w // 2
        fallback_oy = args.origin_y if args.origin_y >= 0 else h // 2
        origin = origin_ref if origin_ref is not None else (fallback_ox, fallback_oy)

        center, bbox, area, _mask = detect_red_center(frame, min_area=args.min_area)

        if center is not None and args.auto_calib and not axis_calibrated:
            origin_ref = origin_below_center(center, args.origin_drop, h)
            origin = origin_ref
            axis_deg = point_to_angle_deg(origin, center)
            axis_calibrated = True
            print(f"[CALIB] auto origin={origin_ref} B-axis={axis_deg:.1f} deg")

        if center is not None and axis_calibrated:
            zone = classify_fan_zone(
                center=center,
                origin=origin,
                axis_deg=axis_deg,
                b_half_deg=args.b_half,
                a_half_deg=args.a_half,
                c_half_deg=args.c_half,
                r_inner=args.r_inner,
                r_outer=args.r_outer,
            )
        else:
            zone = None

        last_zone = zone
        last_center = center
        last_area = area

        vis = draw_fan_overlay(
            frame.copy(),
            center=center,
            bbox=bbox,
            zone=zone,
            area=area,
            origin=origin,
            axis_deg=axis_deg,
            b_half_deg=args.b_half,
            a_half_deg=args.a_half,
            c_half_deg=args.c_half,
            r_inner=args.r_inner,
            r_outer=args.r_outer,
        )

        if not axis_calibrated:
            cv2.putText(vis, "B-axis not calibrated: press c", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (100, 180, 255), 2)
        else:
            cv2.putText(vis, f"B-axis={axis_deg:.1f} deg", (15, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (100, 255, 180), 2)

        cv2.imshow("abc_red_zone_test", vis)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break

        if key == ord("c"):
            if last_center is None:
                print("[CALIB] failed: no red target")
            else:
                origin_ref = origin_below_center(last_center, args.origin_drop, h)
                origin = origin_ref
                axis_deg = point_to_angle_deg(origin, last_center)
                axis_calibrated = True
                print(
                    f"[CALIB] origin={origin_ref} B-axis={axis_deg:.1f} deg "
                    f"(from center={last_center})"
                )

        if key == ord("p"):
            if not axis_calibrated:
                print("[RESULT] NONE (B-axis not calibrated, press c first)")
            elif last_center is None:
                print("[RESULT] NONE (no valid red target)")
            elif last_zone is None:
                cx, cy = last_center
                print(f"[RESULT] OUT (cx={cx}, cy={cy}, area={last_area:.0f})")
            else:
                cx, cy = last_center
                print(f"[RESULT] {last_zone} (cx={cx}, cy={cy}, area={last_area:.0f})")

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
