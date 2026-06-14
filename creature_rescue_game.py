#!/usr/bin/env python3
"""
生灵解救协议 - 多模态游戏GUI
"""

from __future__ import annotations

import argparse
import json
import math
import random
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import cv2
import numpy as np

import tkinter as tk
from tkinter import ttk

try:
    from PIL import Image, ImageTk
except ImportError:
    Image = None
    ImageTk = None

try:
    import sounddevice as sd
except ImportError:
    sd = None


# 配置
FAN_SHRINK_INTERVAL = 4.0
FAN_SHRINK_AMOUNT = 4.0
MIN_FAN_HALF = 6.0
DEFAULT_DIFFICULTY = "normal"
DIFFICULTY_SETTINGS = {
    "easy": {"label": "简单", "fan_half": 28.0, "shrink_interval": 5.0, "shrink_amount": 3.0},
    "normal": {"label": "普通", "fan_half": 22.0, "shrink_interval": 4.0, "shrink_amount": 4.0},
    "hard": {"label": "困难", "fan_half": 16.0, "shrink_interval": 3.0, "shrink_amount": 5.0},
}

LED_CONFIG = {"layout": "col", "rotate": "0", "flip_x": True, "brightness": "0.4"}

BG_DARK = "#0d1117"
BG_CARD = "#161b22"
ACCENT_BLUE = "#58a6ff"
ACCENT_GREEN = "#3fb950"
ACCENT_RED = "#f85149"
ACCENT_YELLOW = "#d29922"
ACCENT_PURPLE = "#a371f7"
TEXT_PRIMARY = "#f0f6fc"
TEXT_SECONDARY = "#8b949e"
CAMERA_VIEW_SIZE = (700, 500)
DEFAULT_WINDOW_WIDTH = 1180
DEFAULT_WINDOW_HEIGHT = 720
MIN_WINDOW_WIDTH = 960
MIN_WINDOW_HEIGHT = 600


@dataclass
class Detection:
    label: str
    conf: float
    box: Tuple[int, int, int, int]


@dataclass
class LogicPuzzle:
    spec_id: str
    question: str
    answer: str
    equations: list
    target_value: int


# 音频录制
class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, device: Optional[str] = None):
        self.rate = sample_rate
        self.device = device
        self._chunks = []
        self._lock = threading.Lock()
        self._stream = None

    def start(self):
        if sd is None:
            raise RuntimeError("sounddevice 未安装，无法录音")

        def callback(indata, frames, t, status):
            with self._lock:
                self._chunks.append(bytes(indata))
        self._stream = sd.RawInputStream(samplerate=self.rate, blocksize=4000, device=self.device,
                                          dtype="int16", channels=1, callback=callback)
        self._stream.start()
        return self.rate

    def stop(self) -> Tuple[bytes, int]:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        with self._lock:
            data = b"".join(self._chunks)
            self._chunks = []
        return data, self.rate


def is_auto_device(value) -> bool:
    return value is None or str(value).strip().lower() in ("", "auto")


def append_unique_device(candidates, value) -> None:
    key = (type(value).__name__, str(value))
    if all((type(existing).__name__, str(existing)) != key for existing in candidates):
        candidates.append(value)


def camera_label(device) -> str:
    return str(device)


def create_camera_capture(device, width: int, height: int):
    if device is None:
        return None

    text = str(device).strip()
    attempts = []
    if text.startswith("/dev/"):
        attempts.append((text, cv2.CAP_V4L2))
        attempts.append((text, None))
    else:
        try:
            attempts.append((int(text), None))
        except ValueError:
            attempts.append((text, None))

    for source, backend in attempts:
        cap = cv2.VideoCapture(source, backend) if backend is not None else cv2.VideoCapture(source)
        if not cap or not cap.isOpened():
            if cap:
                cap.release()
            continue

        cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        cap.set(cv2.CAP_PROP_FPS, 30)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        return cap

    return None


def camera_can_read(device, width: int, height: int) -> bool:
    cap = create_camera_capture(device, width, height)
    if cap is None:
        return False
    try:
        for _ in range(6):
            ok, frame = cap.read()
            if ok and frame is not None and frame.size > 0:
                return True
            time.sleep(0.03)
        return False
    finally:
        cap.release()


def discover_camera_candidates(explicit_device):
    candidates = []
    if not is_auto_device(explicit_device):
        append_unique_device(candidates, explicit_device)

    video_paths = sorted(
        Path("/dev").glob("video*"),
        key=lambda p: int(p.name[5:]) if p.name[5:].isdigit() else 999,
    )
    for path in video_paths:
        append_unique_device(candidates, str(path))

    for idx in range(6):
        append_unique_device(candidates, str(idx))

    return candidates


def resolve_camera_device(requested_device, width: int, height: int):
    requested_auto = is_auto_device(requested_device)
    for candidate in discover_camera_candidates(requested_device):
        if camera_can_read(candidate, width, height):
            if requested_auto:
                return candidate, f"摄像头: 自动选择 {camera_label(candidate)}"
            if str(candidate) == str(requested_device):
                return candidate, f"摄像头: 使用指定设备 {camera_label(candidate)}"
            return candidate, f"摄像头: 指定设备不可用，自动改用 {camera_label(candidate)}"

    if requested_auto:
        return None, "摄像头: 未找到可用设备"
    return None, f"摄像头: 指定设备 {requested_device} 不可用，且未找到可用替代设备"


def audio_label(device) -> str:
    if sd is None:
        return str(device)
    if device is None:
        return "系统默认输入"
    try:
        info = sd.query_devices(device)
        return f"{device} ({info.get('name', 'unknown')})"
    except Exception:
        return str(device)


def audio_can_open(device, sample_rate: int) -> bool:
    if sd is None:
        return False
    stream = None
    try:
        stream = sd.RawInputStream(samplerate=sample_rate, blocksize=4000, device=device,
                                   dtype="int16", channels=1)
        stream.start()
        time.sleep(0.05)
        stream.stop()
        return True
    except Exception:
        return False
    finally:
        if stream is not None:
            try:
                stream.close()
            except Exception:
                pass


def discover_audio_candidates(explicit_device):
    candidates = []
    if not is_auto_device(explicit_device):
        append_unique_device(candidates, explicit_device)

    if sd is None:
        return candidates

    try:
        default_device = sd.default.device
        default_input = default_device[0] if isinstance(default_device, (list, tuple)) else default_device
        if isinstance(default_input, int) and default_input >= 0:
            append_unique_device(candidates, default_input)
    except Exception:
        pass

    try:
        for idx, info in enumerate(sd.query_devices()):
            if int(info.get("max_input_channels", 0)) > 0:
                append_unique_device(candidates, idx)
    except Exception:
        pass

    append_unique_device(candidates, None)
    return candidates


def resolve_audio_device(requested_device, sample_rate: int):
    if sd is None:
        if is_auto_device(requested_device):
            return None, "麦克风: sounddevice 未安装，无法自动探测"
        return requested_device, f"麦克风: sounddevice 未安装，保留指定设备 {requested_device}"

    requested_auto = is_auto_device(requested_device)
    for candidate in discover_audio_candidates(requested_device):
        if audio_can_open(candidate, sample_rate):
            if requested_auto:
                return candidate, f"麦克风: 自动选择 {audio_label(candidate)}"
            if str(candidate) == str(requested_device):
                return candidate, f"麦克风: 使用指定设备 {audio_label(candidate)}"
            return candidate, f"麦克风: 指定设备不可用，自动改用 {audio_label(candidate)}"

    if requested_auto:
        return None, "麦克风: 未找到可用输入设备"
    return None, f"麦克风: 指定设备 {requested_device} 不可用，且未找到可用替代设备"


# 语音识别
def recognize_color_from_pcm(pcm_bytes, sample_rate, model_path=None, grammar_json=None):
    from speech_color import build_grammar_json, extract_color_keyword, load_vosk_runtime
    from vosk import KaldiRecognizer, Model
    model = Model(str(Path(model_path))) if model_path else Model(".")
    recognizer = KaldiRecognizer(model, sample_rate, grammar_json) if grammar_json else KaldiRecognizer(model, sample_rate)
    recognizer.SetWords(False)
    last_text = ""
    for i in range(0, len(pcm_bytes), 4000):
        chunk = pcm_bytes[i:i+4000]
        if recognizer.AcceptWaveform(chunk):
            text = json.loads(recognizer.Result()).get("text", "")
            if text:
                last_text = text
                color = extract_color_keyword(text)
                if color:
                    return color, text
        else:
            partial = json.loads(recognizer.PartialResult()).get("partial", "")
            if partial:
                last_text = partial
    final_text = json.loads(recognizer.FinalResult()).get("text", "") or last_text
    color = extract_color_keyword(final_text)
    return color, final_text


# 红色检测
def detect_red_center(frame_bgr: np.ndarray, min_area: float = 200) -> Tuple[Optional[Tuple[int, int]], float]:
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
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
        return None, 0.0
    c = max(contours, key=cv2.contourArea)
    area = float(cv2.contourArea(c))
    if area < min_area:
        return None, area
    M = cv2.moments(c)
    if M["m00"] == 0:
        return None, area
    cx = int(M["m10"] / M["m00"])
    cy = int(M["m01"] / M["m00"])
    return (cx, cy), area


def classify_fan_zone(center, origin, axis_deg, b_half, a_half, c_half, r_inner, r_outer) -> Optional[str]:
    ox, oy = origin
    cx, cy = center
    dx, dy = cx - ox, cy - oy
    r = math.hypot(dx, dy)
    if r < r_inner or r > r_outer:
        return None
    ang = math.degrees(math.atan2(dy, dx))
    rel = (ang - axis_deg + 180) % 360 - 180
    if abs(rel) <= b_half:
        return "B"
    a_center = b_half + a_half
    if abs(rel - a_center) <= a_half:
        return "A"
    c_center = -(b_half + c_half)
    if abs(rel - c_center) <= c_half:
        return "C"
    return None


# 逻辑题 - A/B/C 等于 0 或 1 共六种目标，每种目标 3 道题
LOGIC_VARS = ("A", "B", "C")


@dataclass(frozen=True)
class LogicPuzzleSpec:
    spec_id: str
    answer: str
    target_value: int
    values: dict
    equations: tuple


LOGIC_PUZZLES = [
    LogicPuzzleSpec("A0-1", "A", 0, {"A": 0, "B": 1, "C": 1}, (
        ("A", "AND", "B", 0),
        ("A", "OR", "C", 1),
        ("B", "AND", "C", 1),
    )),
    LogicPuzzleSpec("A0-2", "A", 0, {"A": 0, "B": 1, "C": 1}, (
        ("A", "AND", "C", 0),
        ("A", "OR", "B", 1),
        ("B", "AND", "C", 1),
    )),
    LogicPuzzleSpec("A0-3", "A", 0, {"A": 0, "B": 1, "C": 1}, (
        ("A", "AND", "B", 0),
        ("A", "AND", "C", 0),
        ("B", "AND", "C", 1),
    )),
    LogicPuzzleSpec("A1-1", "A", 1, {"A": 1, "B": 0, "C": 0}, (
        ("A", "AND", "B", 0),
        ("A", "OR", "B", 1),
        ("B", "OR", "C", 0),
    )),
    LogicPuzzleSpec("A1-2", "A", 1, {"A": 1, "B": 0, "C": 0}, (
        ("A", "AND", "C", 0),
        ("A", "OR", "C", 1),
        ("B", "OR", "C", 0),
    )),
    LogicPuzzleSpec("A1-3", "A", 1, {"A": 1, "B": 0, "C": 0}, (
        ("A", "OR", "B", 1),
        ("A", "OR", "C", 1),
        ("B", "OR", "C", 0),
    )),
    LogicPuzzleSpec("B0-1", "B", 0, {"A": 1, "B": 0, "C": 1}, (
        ("A", "AND", "B", 0),
        ("A", "AND", "C", 1),
        ("B", "AND", "C", 0),
    )),
    LogicPuzzleSpec("B0-2", "B", 0, {"A": 1, "B": 0, "C": 1}, (
        ("A", "OR", "B", 1),
        ("A", "AND", "C", 1),
        ("B", "AND", "C", 0),
    )),
    LogicPuzzleSpec("B0-3", "B", 0, {"A": 1, "B": 0, "C": 1}, (
        ("A", "AND", "C", 1),
        ("B", "AND", "C", 0),
        ("B", "OR", "C", 1),
    )),
    LogicPuzzleSpec("B1-1", "B", 1, {"A": 0, "B": 1, "C": 0}, (
        ("A", "AND", "B", 0),
        ("A", "OR", "C", 0),
        ("B", "OR", "C", 1),
    )),
    LogicPuzzleSpec("B1-2", "B", 1, {"A": 0, "B": 1, "C": 0}, (
        ("A", "OR", "B", 1),
        ("A", "OR", "C", 0),
        ("B", "AND", "C", 0),
    )),
    LogicPuzzleSpec("B1-3", "B", 1, {"A": 0, "B": 1, "C": 0}, (
        ("A", "AND", "C", 0),
        ("A", "OR", "C", 0),
        ("B", "OR", "C", 1),
    )),
    LogicPuzzleSpec("C0-1", "C", 0, {"A": 1, "B": 1, "C": 0}, (
        ("A", "AND", "B", 1),
        ("A", "AND", "C", 0),
        ("B", "AND", "C", 0),
    )),
    LogicPuzzleSpec("C0-2", "C", 0, {"A": 1, "B": 1, "C": 0}, (
        ("A", "AND", "B", 1),
        ("A", "OR", "C", 1),
        ("B", "AND", "C", 0),
    )),
    LogicPuzzleSpec("C0-3", "C", 0, {"A": 1, "B": 1, "C": 0}, (
        ("A", "AND", "B", 1),
        ("A", "AND", "C", 0),
        ("B", "OR", "C", 1),
    )),
    LogicPuzzleSpec("C1-1", "C", 1, {"A": 0, "B": 0, "C": 1}, (
        ("A", "AND", "B", 0),
        ("A", "OR", "B", 0),
        ("A", "OR", "C", 1),
    )),
    LogicPuzzleSpec("C1-2", "C", 1, {"A": 0, "B": 0, "C": 1}, (
        ("A", "OR", "B", 0),
        ("A", "AND", "C", 0),
        ("B", "OR", "C", 1),
    )),
    LogicPuzzleSpec("C1-3", "C", 1, {"A": 0, "B": 0, "C": 1}, (
        ("A", "OR", "B", 0),
        ("A", "OR", "C", 1),
        ("B", "AND", "C", 0),
    )),
]


def format_logic_equation(equation) -> str:
    left, op, right, expected = equation
    return f"{left} {op} {right} = {expected}"


def eval_logic_equation(values, equation) -> bool:
    left, op, right, expected = equation
    if op == "AND":
        actual = values[left] & values[right]
    elif op == "OR":
        actual = values[left] | values[right]
    else:
        raise ValueError(f"Unsupported logic operator: {op}")
    return actual == expected


def iter_logic_assignments():
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                yield {"A": a, "B": b, "C": c}


def validate_logic_puzzle_bank() -> None:
    expected_counts = {(var, value): 0 for var in LOGIC_VARS for value in (0, 1)}
    errors = []

    for puzzle in LOGIC_PUZZLES:
        if puzzle.answer not in LOGIC_VARS:
            errors.append(f"{puzzle.spec_id}: invalid answer {puzzle.answer!r}")
            continue
        if puzzle.target_value not in (0, 1):
            errors.append(f"{puzzle.spec_id}: invalid target value {puzzle.target_value!r}")
            continue

        expected_counts[(puzzle.answer, puzzle.target_value)] += 1
        solutions = [
            values for values in iter_logic_assignments()
            if all(eval_logic_equation(values, equation) for equation in puzzle.equations)
        ]

        if len(solutions) != 1:
            errors.append(f"{puzzle.spec_id}: expected 1 solution, got {solutions}")
            continue

        solution = solutions[0]
        if solution != puzzle.values:
            errors.append(f"{puzzle.spec_id}: solution {solution} != declared {puzzle.values}")

        target_vars = [var for var in LOGIC_VARS if solution[var] == puzzle.target_value]
        if target_vars != [puzzle.answer]:
            errors.append(
                f"{puzzle.spec_id}: target {puzzle.target_value} maps to {target_vars}, "
                f"expected {[puzzle.answer]}"
            )

    for (answer, target_value), count in sorted(expected_counts.items()):
        if count != 3:
            errors.append(f"{answer}={target_value}: expected 3 puzzles, got {count}")

    if errors:
        raise ValueError("Invalid logic puzzle bank:\n" + "\n".join(errors))


validate_logic_puzzle_bank()


def make_logic_puzzle(puzzle: LogicPuzzleSpec) -> LogicPuzzle:
    return LogicPuzzle(
        spec_id=puzzle.spec_id,
        question=f"Which equals {puzzle.target_value}?",
        answer=puzzle.answer,
        equations=[format_logic_equation(equation) for equation in puzzle.equations],
        target_value=puzzle.target_value,
    )


def normalize_final_answer(value: str) -> str:
    return "".join(ch for ch in value.upper() if ch.isalnum())


# LED
def run_led_command(args) -> Tuple[bool, str]:
    script_path = Path(__file__).with_name("ws2812_letters_spi.py")
    base_cmd = [sys.executable, str(script_path)] + args
    commands = [
        base_cmd,
        ["sudo", "-n"] + base_cmd,
    ]
    errors = []

    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        except FileNotFoundError as exc:
            errors.append(f"{cmd[0]} not found: {exc}")
            continue
        except subprocess.TimeoutExpired:
            errors.append(" ".join(cmd[:3]) + " timed out")
            continue

        if result.returncode == 0:
            return True, ""

        stderr = (result.stderr or result.stdout or "").strip()
        errors.append(stderr or f"{' '.join(cmd[:3])} exited with {result.returncode}")

    return False, " | ".join(errors)[-220:]


def led_show_letter(letter: str, color: str = "green") -> Tuple[bool, str]:
    cmd = ["--text", letter, "--color", color,
           "--layout", LED_CONFIG["layout"], "--rotate", LED_CONFIG["rotate"], "--brightness", LED_CONFIG["brightness"]]
    if LED_CONFIG["flip_x"]:
        cmd.append("--flip-x")
    return run_led_command(cmd)


def led_clear() -> Tuple[bool, str]:
    return run_led_command(["--text", " ", "--color", "#000000"])


# 动物检测
class YoloDetector:
    def __init__(self, model_path: str, labels_path: str, conf: float = 0.35):
        from animal_demo.detect_animals17_triggered import YoloDetector as _Orig
        self._detector = _Orig(model_path=Path(model_path), labels_path=Path(labels_path),
                               conf_thres=conf, iou_thres=0.45, det_size=640, threads=2, ort_opt="basic")

    def detect(self, frame):
        det = self._detector.detect_best(frame, None)
        if det:
            return Detection(label=det.label, conf=det.conf, box=det.box)
        return None


# 绘图
def draw_fan_zones(frame, origin, axis_deg, b_half, a_half, c_half, r_inner, r_outer, current_zone=None):
    h, w = frame.shape[:2]
    ox, oy = origin
    cv2.circle(frame, origin, int(r_outer), (100, 150, 200), 2)
    cv2.circle(frame, origin, int(r_inner), (100, 150, 200), 1)
    angles = [axis_deg - (b_half + 2*c_half), axis_deg - b_half, axis_deg + b_half, axis_deg + b_half + 2*a_half]
    for ang in angles:
        rad = math.radians(ang)
        x2 = int(ox + r_outer * math.cos(rad))
        y2 = int(oy + r_outer * math.sin(rad))
        cv2.line(frame, origin, (x2, y2), (80, 200, 200), 2)
    labels = [("C", axis_deg - (b_half + c_half)), ("B", axis_deg), ("A", axis_deg + (b_half + a_half))]
    label_colors = {"A": (100, 200, 255), "B": (100, 255, 100), "C": (255, 180, 100)}
    for label, ang in labels:
        rad = math.radians(ang)
        lx = int(ox + (r_outer + 35) * math.cos(rad))
        ly = int(oy + (r_outer + 35) * math.sin(rad))
        lx = max(30, min(w-30, lx))
        ly = max(30, min(h-30, ly))
        cv2.putText(frame, label, (lx-10, ly+10), cv2.FONT_HERSHEY_SIMPLEX, 1.2, label_colors[label], 3)
    cv2.circle(frame, origin, 10, (180, 255, 180), -1)
    if current_zone:
        color = label_colors.get(current_zone, (255, 255, 255))
        cv2.putText(frame, f"-> {current_zone}", (ox+20, oy-20), cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2)
    return frame


def fit_image_to_canvas(image: Image.Image, canvas_size=CAMERA_VIEW_SIZE) -> Image.Image:
    """Render a camera frame into a fixed-size letterboxed canvas."""
    max_w, max_h = canvas_size
    src_w, src_h = image.size
    if src_w <= 0 or src_h <= 0:
        return Image.new("RGB", canvas_size, "#0d1117")

    scale = min(max_w / src_w, max_h / src_h)
    if scale <= 0:
        scale = 1.0

    out_w = max(1, int(src_w * scale))
    out_h = max(1, int(src_h * scale))
    resized = image.resize((out_w, out_h))
    canvas = Image.new("RGB", canvas_size, "#0d1117")
    canvas.paste(resized, ((max_w - out_w) // 2, (max_h - out_h) // 2))
    return canvas


# 游戏主类
class CreatureRescueGame(tk.Tk):
    def __init__(self, args):
        super().__init__()

        self.cam_w = args.width
        self.cam_h = args.height
        self.audio_rate = args.audio_rate
        self.camera_device, camera_status = resolve_camera_device(args.device, self.cam_w, self.cam_h)
        self.audio_device, audio_status = resolve_audio_device(args.audio_device, self.audio_rate)
        self.device_status = f"{camera_status}；{audio_status}"
        self.vosk_model = args.vosk_model
        self.yolo_model = args.yolo_model
        self.yolo_labels = args.yolo_labels
        self.yolo_conf = args.yolo_conf
        self.window_width = args.window_width
        self.window_height = args.window_height

        # 游戏状态
        self.game_step = 0
        self.color_result = None
        self.animal_result = None
        self.animal_word = ""
        self.current_letter_idx = 0
        self.puzzle: Optional[LogicPuzzle] = None
        self.logic_puzzle_pool = []
        self.difficulty_key = DEFAULT_DIFFICULTY
        self.difficulty_buttons = {}
        self.game_outcome = None
        self.score = 0

        # 时间记录
        self.game_start_time = None

        # 扇形
        self.calibrated = False
        self.fan_origin: Optional[Tuple[int, int]] = None
        self.fan_axis = 0.0
        difficulty = DIFFICULTY_SETTINGS[self.difficulty_key]
        self.fan_b_half = difficulty["fan_half"]
        self.fan_a_half = difficulty["fan_half"]
        self.fan_c_half = difficulty["fan_half"]
        self.fan_shrink_interval = difficulty["shrink_interval"]
        self.fan_shrink_amount = difficulty["shrink_amount"]
        self.min_fan_half = MIN_FAN_HALF
        self.fan_r_inner = 60.0
        self.fan_r_outer = 200.0
        self.fan_current_zone: Optional[str] = None

        self.shrink_timer = None
        self.shrink_remaining = 0.0

        # 音频
        self.recorder: Optional[AudioRecorder] = None
        self.is_recording = False
        self.grammar_json = None

        # 摄像头
        self.cap = None
        self.camera_running = False
        self.last_frame = None

        self.detector = None
        self.captured_frame = None

        # UI元素引用
        self.active_cam_label = None

        self.title("生灵解救协议")
        self.geometry(f"{self.window_width}x{self.window_height}")
        self.minsize(MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT)
        self.configure(bg=BG_DARK)

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.show_step(0)

    def _build_ui(self):
        header = tk.Frame(self, bg="#1f2937", height=60)
        header.pack(fill=tk.X, side=tk.TOP)
        header.pack_propagate(False)
        tk.Label(header, text="🦁 生灵解救协议", font=("Microsoft YaHei", 22, "bold"),
                fg=ACCENT_GREEN, bg="#1f2937").pack(side=tk.LEFT, padx=20, pady=10)
        self.score_lbl = tk.Label(header, text="得分: 0", font=("Microsoft YaHei", 16), fg=ACCENT_YELLOW, bg="#1f2937")
        self.score_lbl.pack(side=tk.RIGHT, padx=30, pady=10)

        progress_frame = tk.Frame(self, bg=BG_DARK, height=50)
        progress_frame.pack(fill=tk.X, side=tk.TOP)
        progress_frame.pack_propagate(False)
        steps = ["开始", "语音", "动物", "标定", "游戏"]
        self.step_labels = []
        for i, step in enumerate(steps):
            lbl = tk.Label(progress_frame, text=f"{i+1}. {step}", font=("Microsoft YaHei", 13), fg=TEXT_SECONDARY, bg=BG_DARK)
            lbl.pack(side=tk.LEFT, padx=30, pady=12)
            self.step_labels.append(lbl)
            if i < len(steps) - 1:
                tk.Label(progress_frame, text="▶", font=("Arial", 12), fg=TEXT_SECONDARY, bg=BG_DARK).pack(side=tk.LEFT, padx=5)

        self.content_frame = tk.Frame(self, bg=BG_DARK)
        self.content_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=15)

        self.status_bar = tk.Label(self, text="▶ 点击开始进入语音识别关卡",
                                  font=("Microsoft YaHei", 14), fg=TEXT_PRIMARY, bg="#2d333b", anchor=tk.W)
        self.status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=15, pady=8)

    def update_progress(self, step):
        for i, lbl in enumerate(self.step_labels):
            if i < step:
                lbl.config(fg=ACCENT_GREEN, font=("Microsoft YaHei", 13))
            elif i == step:
                lbl.config(fg=ACCENT_YELLOW, font=("Microsoft YaHei", 14, "bold"))
            else:
                lbl.config(fg=TEXT_SECONDARY, font=("Microsoft YaHei", 13))

    def set_step_status(self, step):
        messages = {
            0: "▶ 点击开始进入语音识别关卡",
            1: "请通过语音唤醒颜色线索",
            2: "请通过摄像头识别被困生灵",
            3: "请完成云台标定，并选择游戏难度",
            4: "请根据LED字母和逻辑题完成扇形解码",
            5: "关卡结束",
        }
        self.status_bar.config(text=messages.get(step, ""))

    def apply_difficulty_settings(self):
        settings = DIFFICULTY_SETTINGS[self.difficulty_key]
        self.fan_b_half = settings["fan_half"]
        self.fan_a_half = settings["fan_half"]
        self.fan_c_half = settings["fan_half"]
        self.fan_shrink_interval = settings["shrink_interval"]
        self.fan_shrink_amount = settings["shrink_amount"]
        self.min_fan_half = MIN_FAN_HALF

    def select_difficulty(self, key):
        if key not in DIFFICULTY_SETTINGS:
            return
        self.difficulty_key = key
        self.apply_difficulty_settings()
        self.update_difficulty_buttons()
        if hasattr(self, "difficulty_status_lbl") and self.difficulty_status_lbl.winfo_exists():
            settings = DIFFICULTY_SETTINGS[key]
            self.difficulty_status_lbl.config(
                text=f"当前难度：{settings['label']} | 初始扇形 {settings['fan_half']:.0f}° | "
                     f"{settings['shrink_interval']:.0f}s 缩小 {settings['shrink_amount']:.0f}°"
            )

    def update_difficulty_buttons(self):
        for key, btn in self.difficulty_buttons.items():
            selected = key == self.difficulty_key
            btn.config(
                bg=ACCENT_GREEN if selected else "#30363d",
                fg=TEXT_PRIMARY if selected else TEXT_SECONDARY,
                activebackground=ACCENT_GREEN if selected else "#30363d",
            )

    def stop_camera(self):
        self.camera_running = False
        self.active_cam_label = None
        if self.cap:
            try:
                self.cap.release()
            except:
                pass
            self.cap = None

    def start_camera(self, label_widget):
        self.stop_camera()
        self.active_cam_label = label_widget

        if label_widget is None or not label_widget.winfo_exists():
            return

        if self.camera_device is None:
            label_widget.config(text="未找到可用摄像头")
            return

        try:
            self.cap = create_camera_capture(self.camera_device, self.cam_w, self.cam_h)

            if self.cap is not None and self.cap.isOpened():
                self.camera_running = True
                self._camera_loop()
            else:
                if label_widget.winfo_exists():
                    label_widget.config(text="摄像头打开失败")
        except Exception as e:
            if label_widget.winfo_exists():
                label_widget.config(text=f"摄像头错误: {str(e)[:30]}")

    def _camera_loop(self):
        if not self.camera_running or self.cap is None:
            return

        try:
            ok, frame = self.cap.read()
            if ok:
                self.last_frame = frame

                if Image and self.active_cam_label and self.active_cam_label.winfo_exists():
                    vis = frame.copy()

                    # 标定后显示扇形
                    if self.calibrated and self.game_step in [3, 4]:
                        vis = draw_fan_zones(vis, self.fan_origin, self.fan_axis,
                                           self.fan_b_half, self.fan_a_half, self.fan_c_half,
                                           self.fan_r_inner, self.fan_r_outer, self.fan_current_zone)

                    rgb = cv2.cvtColor(vis, cv2.COLOR_BGR2RGB)
                    img = fit_image_to_canvas(Image.fromarray(rgb))
                    tk_img = ImageTk.PhotoImage(img)
                    self.active_cam_label.imglabel = tk_img
                    self.active_cam_label.config(image=tk_img, text="")

                # 检测红色
                if self.calibrated and self.game_step in [3, 4]:
                    center, area = detect_red_center(frame)
                    if center:
                        zone = classify_fan_zone(center, self.fan_origin, self.fan_axis,
                                                self.fan_b_half, self.fan_a_half, self.fan_c_half,
                                                self.fan_r_inner, self.fan_r_outer)
                        self.fan_current_zone = zone
                        if hasattr(self, 'current_zone_lbl') and self.current_zone_lbl.winfo_exists():
                            self.current_zone_lbl.config(text=f"当前扇形: {zone if zone else '外'}")
                    else:
                        self.fan_current_zone = None
                        if hasattr(self, 'current_zone_lbl') and self.current_zone_lbl.winfo_exists():
                            self.current_zone_lbl.config(text="当前扇形: 未检测到")
        except Exception as e:
            pass

        self.after(33, self._camera_loop)

    def show_step(self, step):
        self.stop_camera()

        for widget in self.content_frame.winfo_children():
            widget.destroy()

        self.game_step = step
        self.update_progress(step)
        self.set_step_status(step)

        self.after(50, lambda: self._build_step_page(step))

    def _build_step_page(self, step):
        if self.game_step != step:
            return

        if step == 0:
            self._show_start_screen()
        elif step == 1:
            self._show_speech_screen()
        elif step == 2:
            self._show_animal_screen()
        elif step == 3:
            self._show_calibrate_screen()
        elif step == 4:
            self._show_game_screen()
        elif step == 5:
            self._show_win_screen()

    def make_card(self, parent):
        return tk.Frame(parent, bg=BG_CARD, relief=tk.FLAT, bd=1, highlightbackground="#30363d", highlightthickness=1)

    def make_btn(self, parent, text, command, bg=ACCENT_BLUE, fg=TEXT_PRIMARY, size=14, height=2):
        return tk.Button(parent, text=text, font=("Microsoft YaHei", size, "bold"),
                        bg=bg, fg=fg, activebackground=bg, activeforeground=fg,
                        relief=tk.FLAT, bd=0, cursor="hand2", command=command, height=height)

    # 开始界面
    def _show_start_screen(self):
        card = self.make_card(self.content_frame)
        card.pack(expand=True)
        tk.Label(card, text="🎮", font=("Arial", 60), fg=ACCENT_GREEN, bg=BG_CARD).pack(pady=20)
        tk.Label(card, text="生灵解救协议", font=("Microsoft YaHei", 28, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD).pack(pady=10)
        tk.Label(card, text="通过语音、视觉和操控三位一体，解救被困的生灵", font=("Microsoft YaHei", 14), fg=TEXT_SECONDARY, bg=BG_CARD).pack(pady=5)
        tk.Label(card, text=self.device_status, font=("Microsoft YaHei", 11), fg=TEXT_SECONDARY, bg=BG_CARD,
                 wraplength=780).pack(pady=8, padx=30)
        self.make_btn(card, "▶ 开始游戏", lambda: self.show_step(1), ACCENT_GREEN, TEXT_PRIMARY, 16, 3).pack(pady=30, padx=50)

    # 语音关卡
    def _show_speech_screen(self):
        info = self.make_card(self.content_frame)
        info.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))
        tk.Label(info, text="🎤 第一关：语音识别", font=("Microsoft YaHei", 20, "bold"), fg=ACCENT_BLUE, bg=BG_CARD).pack(pady=20)
        tk.Label(info, text="请说出被困生灵的颜色", font=("Microsoft YaHei", 14), fg=TEXT_PRIMARY, bg=BG_CARD).pack(pady=10)
        tk.Label(info, text='示例："我选择的颜色是蓝色"', font=("Microsoft YaHei", 12), fg=TEXT_SECONDARY, bg=BG_CARD).pack(pady=5)
        self.speech_result_lbl = tk.Label(info, text="等待识别...", font=("Microsoft YaHei", 18, "bold"), fg=TEXT_SECONDARY, bg=BG_CARD)
        self.speech_result_lbl.pack(pady=30)
        btn_frame = tk.Frame(info, bg=BG_CARD)
        btn_frame.pack(pady=20)
        self.btn_start = self.make_btn(btn_frame, "🎙️ 开始录音", self.on_start_recording, ACCENT_GREEN, TEXT_PRIMARY, 14, 2)
        self.btn_start.pack(side=tk.LEFT, padx=10)
        self.btn_stop = self.make_btn(btn_frame, "🛑 停止", self.on_stop_recording, ACCENT_RED, TEXT_PRIMARY, 14, 2)
        self.btn_stop.pack(side=tk.LEFT, padx=10)

        status_card = self.make_card(self.content_frame)
        status_card.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        tk.Label(status_card, text="📋 识别指南", font=("Microsoft YaHei", 16, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD).pack(pady=15)
        for g in ["红色 → red", "蓝色 → blue", "绿色 → green", "黄色 → yellow", "橙色 → orange", "紫色 → purple", "粉色 → pink"]:
            tk.Label(status_card, text=f"• {g}", font=("Microsoft YaHei", 12), fg=TEXT_SECONDARY, bg=BG_CARD, anchor=tk.W).pack(fill=tk.X, padx=20, pady=2)
        self.make_btn(status_card, "➡️ 下一关", lambda: self.show_step(2), ACCENT_BLUE, TEXT_PRIMARY, 14, 2).pack(pady=20, padx=20)

    def on_start_recording(self):
        try:
            self.recorder = AudioRecorder(self.audio_rate, self.audio_device)
            self.recorder.start()
            self.is_recording = True
            self.btn_start.config(state=tk.DISABLED)
            self.btn_stop.config(state=tk.NORMAL)
            self.speech_result_lbl.config(text="正在录音...", fg=ACCENT_YELLOW)
        except Exception as e:
            self.speech_result_lbl.config(text=f"录音失败: {e}", fg=ACCENT_RED)

    def on_stop_recording(self):
        if not self.is_recording or not self.recorder:
            return
        audio_bytes, rate = self.recorder.stop()
        self.is_recording = False
        self.btn_stop.config(state=tk.DISABLED)
        self.speech_result_lbl.config(text="识别中...", fg=ACCENT_BLUE)
        threading.Thread(target=self.recognize_speech, args=(audio_bytes, rate), daemon=True).start()

    def recognize_speech(self, audio_bytes, rate):
        try:
            color, text = recognize_color_from_pcm(audio_bytes, rate, self.vosk_model, self.grammar_json)
            self.after(0, lambda c=color, t=text: self.on_speech_result(c, t))
        except Exception as e:
            err = str(e)
            self.after(0, lambda e=err: self.on_speech_result(None, e))

    def on_speech_result(self, color, text):
        if color:
            self.color_result = color
            self.speech_result_lbl.config(text="识别成功\n颜色线索已封存", fg=ACCENT_GREEN)
            self.status_bar.config(text="✅ 颜色识别完成，线索已封存")
        else:
            self.speech_result_lbl.config(text=f"未识别到颜色\n尝试: {text[:20] if text else '无'}", fg=ACCENT_RED)
            self.btn_start.config(state=tk.NORMAL)

    # 动物识别关卡
    def _show_animal_screen(self):
        cam_card = self.make_card(self.content_frame)
        cam_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        animal_toolbar = tk.Frame(cam_card, bg=BG_CARD)
        animal_toolbar.pack(fill=tk.X, padx=10, pady=10)
        tk.Label(animal_toolbar, text="📷 第二关：动物识别", font=("Microsoft YaHei", 18, "bold"),
                 fg=ACCENT_GREEN, bg=BG_CARD).pack(side=tk.LEFT)
        self.make_btn(animal_toolbar, "📸 识别此画面", self.on_capture_animal,
                      ACCENT_GREEN, TEXT_PRIMARY, 12, 1).pack(side=tk.RIGHT)

        self.cam_label = tk.Label(cam_card, text="摄像头启动中...", font=("Microsoft YaHei", 14), fg=TEXT_SECONDARY, bg="#0d1117")
        self.cam_label.pack(pady=(0, 10), padx=10, fill=tk.BOTH, expand=True)

        info_card = self.make_card(self.content_frame)
        info_card.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        tk.Label(info_card, text="📋 识别结果", font=("Microsoft YaHei", 16, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD).pack(pady=10)
        self.captured_label = tk.Label(info_card, text="点击「识别此画面」\n拍摄照片", font=("Microsoft YaHei", 12), fg=TEXT_SECONDARY, bg="#0d1117", justify=tk.CENTER)
        self.captured_label.pack(pady=10, padx=10, fill=tk.BOTH, expand=True)
        self.animal_result_lbl = tk.Label(info_card, text="", font=("Microsoft YaHei", 20, "bold"), fg=TEXT_SECONDARY, bg=BG_CARD)
        self.animal_result_lbl.pack(pady=10)
        self.next_btn = self.make_btn(info_card, "➡️ 下一关", self.on_next_from_animal, ACCENT_BLUE, TEXT_PRIMARY, 14, 2)
        self.next_btn.pack(pady=15, padx=20)

        self.start_camera(self.cam_label)

    def on_capture_animal(self):
        if self.last_frame is None:
            self.status_bar.config(text="⚠️ 未获取到画面")
            return
        self.captured_frame = self.last_frame.copy()
        if Image and self.captured_frame is not None:
            try:
                rgb = cv2.cvtColor(self.captured_frame, cv2.COLOR_BGR2RGB)
                img = Image.fromarray(rgb).resize((350, 250))
                tk_img = ImageTk.PhotoImage(img)
                self.captured_label.imglabel = tk_img
                self.captured_label.config(image=tk_img, text="", fg=TEXT_PRIMARY)
            except Exception:
                pass
        self.animal_result_lbl.config(text="识别中...", fg=ACCENT_YELLOW)
        threading.Thread(target=self.detect_animal, daemon=True).start()

    def detect_animal(self):
        try:
            if self.detector is None:
                self.detector = YoloDetector(self.yolo_model, self.yolo_labels, self.yolo_conf)
            det = self.detector.detect(self.captured_frame)
            self.after(0, lambda d=det: self.on_animal_result(d))
        except Exception as e:
            err = str(e)
            self.after(0, lambda e=err: self.on_animal_result(None, e))

    def on_animal_result(self, detection, error=None):
        if error:
            self.animal_result_lbl.config(text="识别失败", fg=ACCENT_RED)
            self.status_bar.config(text=f"⚠️ {error[:30]}")
            return
        if detection:
            self.animal_result = detection.label.lower()
            self.animal_word = self.animal_result.upper()
            self.animal_result_lbl.config(text=f"识别成功\n身份已封存\n置信度: {detection.conf:.0%}", fg=ACCENT_GREEN)
            self.status_bar.config(text="✅ 动物识别完成，身份已封存")
        else:
            self.animal_result_lbl.config(text="未检测到动物", fg=ACCENT_RED)
            self.status_bar.config(text="⚠️ 未检测到动物，请重试")

    def on_next_from_animal(self):
        if self.animal_result is None:
            self.status_bar.config(text="⚠️ 请先识别动物再继续")
            return
        self.show_step(3)

    # 标定关卡
    def _show_calibrate_screen(self):
        cam_card = self.make_card(self.content_frame)
        cam_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        calib_toolbar = tk.Frame(cam_card, bg=BG_CARD)
        calib_toolbar.pack(fill=tk.X, padx=10, pady=10)
        tk.Label(calib_toolbar, text="🎯 第三关：云台标定", font=("Microsoft YaHei", 18, "bold"),
                 fg=ACCENT_PURPLE, bg=BG_CARD).pack(side=tk.LEFT)
        self.make_btn(calib_toolbar, "🎯 标定此位置", self.on_calibrate,
                      ACCENT_PURPLE, TEXT_PRIMARY, 12, 1).pack(side=tk.RIGHT)

        calib_cam_frame = tk.Frame(cam_card, width=CAMERA_VIEW_SIZE[0], height=CAMERA_VIEW_SIZE[1], bg="#0d1117")
        calib_cam_frame.pack(pady=(0, 10), padx=10)
        calib_cam_frame.pack_propagate(False)
        self.calib_cam_label = tk.Label(calib_cam_frame, text="请将云台红色方块移到画面中央",
                                        font=("Microsoft YaHei", 14), fg=TEXT_SECONDARY, bg="#0d1117")
        self.calib_cam_label.pack(fill=tk.BOTH, expand=True)
        self.calib_status_lbl = tk.Label(cam_card, text="等待标定...", font=("Microsoft YaHei", 14), fg=TEXT_SECONDARY, bg=BG_CARD)
        self.calib_status_lbl.pack(pady=5)

        info_card = self.make_card(self.content_frame)
        info_card.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        tk.Label(info_card, text="📋 标定说明", font=("Microsoft YaHei", 16, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD).pack(pady=15)
        tk.Label(info_card, text="1. 将云台红色方块放到画面中央\n2. 点击「标定此位置」\n3. 系统将显示扇形划分", font=("Microsoft YaHei", 12), fg=TEXT_SECONDARY, bg=BG_CARD, justify=tk.LEFT).pack(pady=10, padx=20)

        difficulty_frame = tk.Frame(info_card, bg=BG_CARD)
        difficulty_frame.pack(fill=tk.X, padx=20, pady=12)
        tk.Label(difficulty_frame, text="选择难度", font=("Microsoft YaHei", 14, "bold"),
                 fg=ACCENT_YELLOW, bg=BG_CARD).pack(anchor=tk.W, pady=(0, 8))
        difficulty_btn_frame = tk.Frame(difficulty_frame, bg=BG_CARD)
        difficulty_btn_frame.pack(fill=tk.X)
        self.difficulty_buttons = {}
        for key, settings in DIFFICULTY_SETTINGS.items():
            btn = self.make_btn(difficulty_btn_frame, settings["label"],
                                lambda k=key: self.select_difficulty(k),
                                "#30363d", TEXT_SECONDARY, 11, 1)
            btn.pack(side=tk.LEFT, padx=(0, 8))
            self.difficulty_buttons[key] = btn
        self.difficulty_status_lbl = tk.Label(difficulty_frame, text="", font=("Microsoft YaHei", 11),
                                              fg=TEXT_SECONDARY, bg=BG_CARD, justify=tk.LEFT)
        self.difficulty_status_lbl.pack(anchor=tk.W, pady=(8, 0))
        self.select_difficulty(self.difficulty_key)

        self.calib_next_btn = self.make_btn(info_card, "➡️ 开始游戏", lambda: self.show_step(4), ACCENT_GREEN, TEXT_PRIMARY, 14, 2)
        self.calib_next_btn.pack(pady=20, padx=20)
        self.calib_next_btn.config(state=tk.DISABLED)

        self.start_camera(self.calib_cam_label)

    def on_calibrate(self):
        if self.last_frame is None:
            self.calib_status_lbl.config(text="未获取到画面", fg=ACCENT_RED)
            return
        center, area = detect_red_center(self.last_frame)
        if center is None:
            self.calib_status_lbl.config(text="未检测到红色方块", fg=ACCENT_RED)
            return
        h, w = self.last_frame.shape[:2]
        drop = 150
        oy = min(h - 1, center[1] + drop)
        self.fan_origin = (center[0], oy)
        dx = center[0] - self.fan_origin[0]
        dy = center[1] - self.fan_origin[1]
        self.fan_axis = math.degrees(math.atan2(dy, dx))
        self.calibrated = True
        self.calib_status_lbl.config(text=f"标定成功！B轴={self.fan_axis:.1f}°\n扇形已显示", fg=ACCENT_GREEN)
        self.calib_next_btn.config(state=tk.NORMAL)
        self.status_bar.config(text="✅ 标定完成！请选择难度后开始游戏")

    # 游戏关卡
    def _show_game_screen(self):
        # 记录游戏开始时间
        if self.game_start_time is None:
            self.game_start_time = time.time()

        cam_card = self.make_card(self.content_frame)
        cam_card.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        game_toolbar = tk.Frame(cam_card, bg=BG_CARD)
        game_toolbar.pack(fill=tk.X, padx=10, pady=10)
        tk.Label(game_toolbar, text="🎮 游戏进行中", font=("Microsoft YaHei", 18, "bold"),
                 fg=ACCENT_YELLOW, bg=BG_CARD).pack(side=tk.LEFT)
        self.make_btn(game_toolbar, "✅ 锁定并判定", self.on_confirm_position,
                      ACCENT_GREEN, TEXT_PRIMARY, 12, 1).pack(side=tk.RIGHT)

        game_cam_frame = tk.Frame(cam_card, width=CAMERA_VIEW_SIZE[0], height=CAMERA_VIEW_SIZE[1], bg="#0d1117")
        game_cam_frame.pack(pady=(0, 10), padx=10)
        game_cam_frame.pack_propagate(False)
        self.game_cam_label = tk.Label(game_cam_frame, text="游戏画面", font=("Microsoft YaHei", 14),
                                       fg=TEXT_SECONDARY, bg="#0d1117")
        self.game_cam_label.pack(fill=tk.BOTH, expand=True)
        self.word_progress_lbl = tk.Label(cam_card, text="", font=("Consolas", 20, "bold"), fg=ACCENT_GREEN, bg=BG_CARD)
        self.word_progress_lbl.pack(pady=10)

        info_card = self.make_card(self.content_frame)
        info_card.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(10, 0))
        tk.Label(info_card, text="📋 任务信息", font=("Microsoft YaHei", 16, "bold"), fg=TEXT_PRIMARY, bg=BG_CARD).pack(pady=10)
        difficulty = DIFFICULTY_SETTINGS[self.difficulty_key]
        tk.Label(info_card, text=f"难度: {difficulty['label']}", font=("Microsoft YaHei", 14),
                 fg=ACCENT_YELLOW, bg=BG_CARD).pack(pady=5)
        tk.Label(info_card, text="颜色线索与生灵身份已封存", font=("Microsoft YaHei", 12),
                 fg=TEXT_SECONDARY, bg=BG_CARD).pack(pady=5)

        puzzle_frame = tk.Frame(info_card, bg="#1a2a3a", relief=tk.RAISED, bd=1)
        puzzle_frame.pack(fill=tk.X, padx=15, pady=10)
        tk.Label(puzzle_frame, text="🧩 逻辑题", font=("Microsoft YaHei", 14, "bold"), fg=ACCENT_PURPLE, bg="#1a2a3a").pack(pady=5)
        self.puzzle_lbl = tk.Label(puzzle_frame, text="", font=("Consolas", 12), fg=TEXT_PRIMARY, bg="#1a2a3a", justify=tk.LEFT)
        self.puzzle_lbl.pack(pady=5, padx=10)
        self.target_zone_lbl = tk.Label(puzzle_frame, text="目标扇形: ???", font=("Microsoft YaHei", 18, "bold"), fg=ACCENT_GREEN, bg="#1a2a3a")
        self.target_zone_lbl.pack(pady=10)

        self.timer_lbl = tk.Label(info_card, text="", font=("Microsoft YaHei", 12), fg=ACCENT_RED, bg=BG_CARD)
        self.timer_lbl.pack(pady=10)
        self.current_zone_lbl = tk.Label(info_card, text="当前扇形: --", font=("Microsoft YaHei", 14), fg=TEXT_SECONDARY, bg=BG_CARD)
        self.current_zone_lbl.pack(pady=10)

        # 最终答案输入区
        final_frame = tk.Frame(info_card, bg="#2a1a3a", relief=tk.RAISED, bd=1)
        final_frame.pack(fill=tk.X, padx=15, pady=10)
        tk.Label(final_frame, text="🔑 最终答案（颜色+动物名）", font=("Microsoft YaHei", 14, "bold"), fg=ACCENT_YELLOW, bg="#2a1a3a").pack(pady=5)
        self.final_answer_entry = tk.Entry(final_frame, font=("Microsoft YaHei", 16), bg="#1a0a2a", fg=ACCENT_GREEN,
                                           insertbackground=ACCENT_GREEN, relief=tk.FLAT, bd=5, justify=tk.CENTER)
        self.final_answer_entry.pack(pady=5, padx=10, fill=tk.X)
        self.make_btn(final_frame, "🚀 提交最终答案", self.on_submit_final_answer, ACCENT_PURPLE, TEXT_PRIMARY, 12, 1).pack(pady=5)

        self.start_game_logic()
        self.start_camera(self.game_cam_label)

    def start_game_logic(self):
        letter = self.animal_word[0]
        color = self.color_result if self.color_result else "green"
        led_ok, led_msg = led_show_letter(letter, color)
        print(f"[FINAL_TEST] 最终口令={normalize_final_answer(color + self.animal_word)}", flush=True)
        self.reset_logic_puzzle_pool()
        self.generate_new_puzzle()
        self.start_shrink_timer()
        self.update_word_display()
        if led_ok:
            self.status_bar.config(text="LED已显示当前字母，请完成逻辑题")
        else:
            self.status_bar.config(text=f"LED启动失败：{led_msg}")

    def reset_logic_puzzle_pool(self):
        self.logic_puzzle_pool = list(LOGIC_PUZZLES)
        random.shuffle(self.logic_puzzle_pool)

    def generate_new_puzzle(self):
        if not self.logic_puzzle_pool:
            self.reset_logic_puzzle_pool()
        self.puzzle = make_logic_puzzle(self.logic_puzzle_pool.pop())
        print(
            f"[LOGIC_TEST] 题目 {self.puzzle.spec_id} | 目标值={self.puzzle.target_value} | "
            f"答案扇形={self.puzzle.answer}",
            flush=True,
        )
        eq_text = "\n".join(self.puzzle.equations)
        self.puzzle_lbl.config(text=f"{eq_text}\n\n{self.puzzle.question}")
        self.target_zone_lbl.config(text="目标扇形: ???")

    def update_word_display(self):
        if not self.animal_word:
            return
        total = len(self.animal_word)
        current = min(self.current_letter_idx + 1, total)
        self.word_progress_lbl.config(text=f"字母进度: {current}/{total}")

    def start_shrink_timer(self):
        self.shrink_remaining = self.fan_shrink_interval
        self.update_timer_display()
        def tick():
            if self.game_step != 4:
                return
            self.shrink_remaining -= 0.1
            self.update_timer_display()
            if self.shrink_remaining <= 0:
                self.shrink_fans()
                self.shrink_remaining = self.fan_shrink_interval
            self.shrink_timer = self.after(100, tick)
        self.shrink_timer = self.after(100, tick)

    def update_timer_display(self):
        bars = int(self.shrink_remaining / self.fan_shrink_interval * 10)
        bar_str = "█" * bars + "░" * (10 - bars)
        self.timer_lbl.config(text=f"缩小倒计时: {bar_str} {self.shrink_remaining:.1f}s")

    def shrink_fans(self):
        if self.fan_b_half > self.min_fan_half:
            new_half = max(self.min_fan_half, self.fan_b_half - self.fan_shrink_amount)
            self.fan_b_half = new_half
            self.fan_a_half = new_half
            self.fan_c_half = new_half
            self.status_bar.config(text=f"⚠️ 扇形缩小！当前: {self.fan_b_half:.0f}°")
        else:
            self.on_game_over()

    def detect_locked_zone(self) -> Tuple[Optional[str], Optional[str]]:
        """Re-detect the red block on the latest frame when the player locks position."""
        if self.last_frame is None:
            return None, "未获取到画面"
        if not self.calibrated or self.fan_origin is None:
            return None, "尚未完成标定"

        center, _ = detect_red_center(self.last_frame)
        if center is None:
            self.fan_current_zone = None
            if hasattr(self, 'current_zone_lbl') and self.current_zone_lbl.winfo_exists():
                self.current_zone_lbl.config(text="当前扇形: 未检测到")
            return None, "未检测到红色方块"

        zone = classify_fan_zone(center, self.fan_origin, self.fan_axis,
                                 self.fan_b_half, self.fan_a_half, self.fan_c_half,
                                 self.fan_r_inner, self.fan_r_outer)
        self.fan_current_zone = zone
        if hasattr(self, 'current_zone_lbl') and self.current_zone_lbl.winfo_exists():
            self.current_zone_lbl.config(text=f"当前扇形: {zone if zone else '外'}")
        if zone is None:
            return None, "红色方块不在A/B/C扇形内"
        return zone, None

    def on_confirm_position(self):
        """玩家确认位置后检查是否正确"""
        if self.puzzle is None:
            return

        zone, error = self.detect_locked_zone()
        if error:
            self.status_bar.config(text=f"❌ {error}")
            return

        if zone == self.puzzle.answer:
            # 答对了
            self.score += 10
            self.score_lbl.config(text=f"得分: {self.score}")
            if self.shrink_timer:
                self.after_cancel(self.shrink_timer)

            self.current_letter_idx += 1
            if self.current_letter_idx >= len(self.animal_word):
                # 所有字母完成
                self.update_word_display()
                self.target_zone_lbl.config(text=f"✅ 正确！", fg=ACCENT_GREEN)
                self.status_bar.config(text="✅ 所有字母完成！请输入颜色+动物名最终答案！")
            else:
                letter = self.animal_word[self.current_letter_idx]
                color = self.color_result if self.color_result else "green"
                led_ok, led_msg = led_show_letter(letter, color)
                self.generate_new_puzzle()
                self.update_word_display()
                self.start_shrink_timer()
                if led_ok:
                    self.status_bar.config(text=f"正确！LED已显示下一个字母（剩余题目: {len(self.logic_puzzle_pool)}）")
                else:
                    self.status_bar.config(text=f"正确，但LED失败：{led_msg}")
        else:
            # 答错了
            self.status_bar.config(text=f"❌ 错误！当前扇形: {zone or '外'}, 请重新选择")

    def on_submit_final_answer(self):
        """提交最终答案"""
        user_answer = normalize_final_answer(self.final_answer_entry.get())
        color = self.color_result if self.color_result else "green"
        expected_answer = normalize_final_answer(color + self.animal_word)
        if user_answer == expected_answer:
            self.on_game_win()
        else:
            self.status_bar.config(text="❌ 答案错误！请按颜色+动物名重新尝试")

    def on_game_win(self):
        self.game_step = 5
        self.game_outcome = "win"
        if self.shrink_timer:
            self.after_cancel(self.shrink_timer)
        led_clear()

        # 计算通关时长
        elapsed = time.time() - self.game_start_time if self.game_start_time else 0
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        self.target_zone_lbl.config(text=f"🎉 恭喜通关！", fg=ACCENT_GREEN)
        self.puzzle_lbl.config(text=f"生灵解放成功\n用时: {minutes}分{seconds}秒")
        self.status_bar.config(text=f"🎊 游戏胜利！用时 {minutes}分{seconds}秒")
        self.after(5000, lambda: self.show_step(5))

    def on_game_over(self):
        self.game_step = 5
        self.game_outcome = "fail"
        if self.shrink_timer:
            self.after_cancel(self.shrink_timer)
        led_clear()

        elapsed = time.time() - self.game_start_time if self.game_start_time else 0
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        self.target_zone_lbl.config(text=f"⏰ 时间到！", fg=ACCENT_RED)
        self.puzzle_lbl.config(text=f"解放失败\n用时: {minutes}分{seconds}秒")
        self.status_bar.config(text=f"⏰ 游戏结束！用时 {minutes}分{seconds}秒")
        self.after(3000, lambda: self.show_step(5))

    # 胜利界面
    def _show_win_screen(self):
        won = self.game_outcome != "fail"
        card = self.make_card(self.content_frame)
        card.pack(expand=True)
        tk.Label(card, text="🎉" if won else "⏰", font=("Arial", 60),
                 fg=ACCENT_GREEN if won else ACCENT_RED, bg=BG_CARD).pack(pady=20)
        tk.Label(card, text="生灵获救！" if won else "解放失败",
                 font=("Microsoft YaHei", 32, "bold"),
                 fg=ACCENT_GREEN if won else ACCENT_RED, bg=BG_CARD).pack(pady=10)

        elapsed = time.time() - self.game_start_time if self.game_start_time else 0
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)

        summary = "最终密码已验证" if won else "最终密码未能解锁"
        tk.Label(card, text=summary, font=("Microsoft YaHei", 20), fg=TEXT_PRIMARY, bg=BG_CARD).pack(pady=10)
        tk.Label(card, text=f"通关用时: {minutes}分{seconds}秒", font=("Microsoft YaHei", 18, "bold"), fg=ACCENT_YELLOW, bg=BG_CARD).pack(pady=20)
        btn_frame = tk.Frame(card, bg=BG_CARD)
        btn_frame.pack(pady=30)
        self.make_btn(btn_frame, "🔄 重新开始", self.reset_game, ACCENT_BLUE, TEXT_PRIMARY, 14, 2).pack(side=tk.LEFT, padx=10)
        self.make_btn(btn_frame, "🚪 退出", self.on_close, ACCENT_RED, TEXT_PRIMARY, 14, 2).pack(side=tk.LEFT, padx=10)

    def reset_game(self):
        self.game_step = 0
        self.color_result = None
        self.animal_result = None
        self.animal_word = ""
        self.current_letter_idx = 0
        self.score = 0
        self.game_start_time = None
        self.calibrated = False
        self.puzzle = None
        self.logic_puzzle_pool = []
        self.fan_current_zone = None
        self.game_outcome = None
        self.difficulty_key = DEFAULT_DIFFICULTY
        self.apply_difficulty_settings()
        if self.shrink_timer:
            self.after_cancel(self.shrink_timer)
        self.stop_camera()
        led_clear()
        self.score_lbl.config(text="得分: 0")
        self.show_step(0)

    def on_close(self):
        if self.shrink_timer:
            self.after_cancel(self.shrink_timer)
        self.stop_camera()
        led_clear()
        self.destroy()


def parse_args():
    ap = argparse.ArgumentParser(description="生灵解救协议")
    ap.add_argument("--device", default="auto", help="摄像头设备，如 /dev/video0；默认 auto 自动探测")
    ap.add_argument("--width", type=int, default=640)
    ap.add_argument("--height", type=int, default=480)
    ap.add_argument("--window-width", type=int, default=DEFAULT_WINDOW_WIDTH)
    ap.add_argument("--window-height", type=int, default=DEFAULT_WINDOW_HEIGHT)
    ap.add_argument("--audio-device", default="auto", help="麦克风输入设备；默认 auto 自动探测")
    ap.add_argument("--audio-rate", type=int, default=16000)
    ap.add_argument("--vosk-model", default=None)
    ap.add_argument("--yolo-model", default="model_artifacts/deploy_pack_20260507/animals17_best.onnx")
    ap.add_argument("--yolo-labels", default="model_artifacts/deploy_pack_20260507/labels.txt")
    ap.add_argument("--yolo-conf", type=float, default=0.35)
    return ap.parse_args()


if __name__ == "__main__":
    args = parse_args()
    app = CreatureRescueGame(args)
    app.mainloop()
