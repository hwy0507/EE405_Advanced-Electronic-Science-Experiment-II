"""Recognize a spoken Chinese color sentence and print the color in English.

Expected sentence example:
    我选择的颜色是蓝色

Orange Pi usage:
    python3 speech_color.py --model ./vosk-model-small-cn-0.22
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, Optional, Tuple


COLOR_PATTERNS: Dict[str, Iterable[str]] = {
    "pink": (r"粉红色?", r"粉色?", r"\bpink\b"),
    "gray": (r"灰白色?", r"灰色?", r"\bgray\b", r"\bgrey\b"),
    "brown": (r"咖啡色?", r"棕色?", r"\bbrown\b"),
    "orange": (r"橙色?", r"橘色?", r"桔色?", r"\borange\b"),
    "purple": (r"紫色?", r"\bpurple\b"),
    "red": (r"红色?", r"赤色?", r"\bred\b"),
    "green": (r"绿色?", r"青色?", r"\bgreen\b"),
    "blue": (r"蓝色?", r"天蓝色?", r"\bblue\b"),
    "yellow": (r"黄色?", r"金黄色?", r"\byellow\b"),
    "black": (r"黑色?", r"\bblack\b"),
    "white": (r"白色?", r"\bwhite\b"),
}

GRAMMAR_COLOR_WORDS = [
    "红色",
    "赤色",
    "绿色",
    "青色",
    "蓝色",
    "天蓝色",
    "黄色",
    "金黄色",
    "橙色",
    "橘色",
    "紫色",
    "粉色",
    "粉红色",
    "黑色",
    "白色",
    "灰色",
    "灰白色",
    "棕色",
    "咖啡色",
]

GRAMMAR_TEMPLATES = [
    "我 选择 的 颜色 是 {color}",
    "我 选择 颜色 是 {color}",
    "我 选 的 颜色 是 {color}",
    "我 选 的 是 {color}",
    "选择 的 颜色 是 {color}",
    "颜色 是 {color}",
]

NOISE_WORDS = (
    "我选择的颜色是",
    "我选择颜色是",
    "我选的颜色是",
    "我选的是",
    "选择的颜色是",
    "颜色是",
    "就是",
    "嗯",
    "啊",
    "呃",
)


def normalize_text(text: str) -> str:
    """Normalize ASR text before color keyword matching."""
    text = text.lower()
    text = text.replace("紅", "红").replace("綠", "绿").replace("藍", "蓝").replace("黃", "黄")
    # Vosk Chinese may insert spaces between words or characters.
    text = re.sub(r"[\s，。,.!?！？：:；;\"'“”‘’、]+", "", text)
    for noise in NOISE_WORDS:
        text = text.replace(noise, "")
    return text.strip()


def extract_color_keyword(text: str, default: Optional[str] = None) -> Optional[str]:
    """Extract an English color keyword from Chinese or English text."""
    normalized = normalize_text(text)
    for color, patterns in COLOR_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, normalized):
                return color
    return default


def _import_vosk_libs():
    try:
        from vosk import KaldiRecognizer, Model, SetLogLevel
    except ImportError as exc:
        raise RuntimeError(
            "缺少语音识别依赖。请先安装：\n"
            "  python3 -m pip install vosk"
        ) from exc
    return KaldiRecognizer, Model, SetLogLevel


def _import_audio_libs():
    try:
        import sounddevice as sd
    except ImportError as exc:
        raise RuntimeError(
            "缺少麦克风录音依赖。请先安装：\n"
            "  sudo apt install -y portaudio19-dev libportaudio2\n"
            "  python3 -m pip install sounddevice"
        ) from exc
    KaldiRecognizer, Model, SetLogLevel = _import_vosk_libs()
    return sd, KaldiRecognizer, Model, SetLogLevel


def _resolve_model_path(model_path: Optional[str]) -> Path:
    candidates = []
    if model_path:
        candidates.append(Path(model_path).expanduser())
    if os.environ.get("VOSK_MODEL_PATH"):
        candidates.append(Path(os.environ["VOSK_MODEL_PATH"]).expanduser())
    candidates.extend(
        [
            Path("vosk-model-small-cn-0.22"),
            Path("models/vosk-model-small-cn-0.22"),
            Path("/private/tmp/vosk-model-small-cn-0.22"),
        ]
    )

    for candidate in candidates:
        if candidate.exists():
            return candidate

    tried = "\n  ".join(str(path) for path in candidates)
    raise FileNotFoundError(
        "找不到 Vosk 中文模型目录。请下载并解压 vosk-model-small-cn-0.22，"
        "然后用 --model 指定路径。\n已尝试：\n  "
        f"{tried}"
    )


def _parse_device(device: Optional[str]):
    if device is None:
        return None
    return int(device) if device.isdigit() else device


def _resolve_input_sample_rate(
    sd, device: Optional[str], requested_rate: int, verbose: bool = False
) -> int:
    """
    Pick a usable input sample rate for the selected device.
    If requested_rate is unsupported, fall back to device default samplerate.
    """
    parsed_device = _parse_device(device)
    try:
        sd.check_input_settings(
            device=parsed_device,
            channels=1,
            dtype="int16",
            samplerate=requested_rate,
        )
        return requested_rate
    except Exception:
        pass

    info = sd.query_devices(parsed_device, "input")
    fallback_rate = int(round(float(info["default_samplerate"])))
    if verbose:
        print(
            f"[audio] 设备不支持 {requested_rate} Hz，自动切换到 {fallback_rate} Hz",
            file=sys.stderr,
        )
    sd.check_input_settings(
        device=parsed_device,
        channels=1,
        dtype="int16",
        samplerate=fallback_rate,
    )
    return fallback_rate


def load_vosk_runtime(model_path: Optional[str] = None) -> Tuple[object, object]:
    """Load Vosk model once and return (KaldiRecognizerClass, model_instance)."""
    KaldiRecognizer, Model, SetLogLevel = _import_vosk_libs()
    SetLogLevel(-1)
    resolved_model = _resolve_model_path(model_path)
    model = Model(str(resolved_model))
    return KaldiRecognizer, model


def build_grammar_json(use_default_grammar: bool) -> Optional[str]:
    """Return grammar json for constrained decoding."""
    if not use_default_grammar:
        return None
    grammar_list = []
    for color_word in GRAMMAR_COLOR_WORDS:
        grammar_list.append(color_word)
        for template in GRAMMAR_TEMPLATES:
            grammar_list.append(template.format(color=color_word))
    grammar_list.append("[unk]")
    # Keep order but remove duplicates.
    grammar_list = list(dict.fromkeys(grammar_list))
    return json.dumps(grammar_list, ensure_ascii=False)


def recognize_color_from_microphone(
    model_path: Optional[str] = None,
    timeout_sec: float = 8.0,
    sample_rate: int = 16000,
    device: Optional[str] = None,
    verbose: bool = False,
    vosk_runtime: Optional[Tuple[object, object]] = None,
    grammar_json: Optional[str] = None,
    prompt_delay_sec: float = 5.0,
) -> Tuple[str, str]:
    """Listen to the microphone once and return (english_color, recognized_text)."""
    sd, _, _, _ = _import_audio_libs()
    if vosk_runtime is None:
        KaldiRecognizer, model = load_vosk_runtime(model_path)
    else:
        KaldiRecognizer, model = vosk_runtime
    capture_rate = _resolve_input_sample_rate(sd, device, sample_rate, verbose=verbose)
    audio_queue: "queue.Queue[bytes]" = queue.Queue()

    def audio_callback(indata, frames, callback_time, status):
        if status and verbose:
            print(f"[audio] {status}", file=sys.stderr)
        audio_queue.put(bytes(indata))

    recognizer = (
        KaldiRecognizer(model, capture_rate, grammar_json)
        if grammar_json
        else KaldiRecognizer(model, capture_rate)
    )
    recognizer.SetWords(False)

    # User guidance + fixed wait before recording starts.
    print("请开始说指令：", file=sys.stderr)
    if prompt_delay_sec > 0:
        print(f"{prompt_delay_sec:.1f} 秒后开始采集...", file=sys.stderr)
        time.sleep(prompt_delay_sec)
    print("开始采集，请说话", file=sys.stderr)

    deadline = time.monotonic() + timeout_sec
    audio_chunks = []
    with sd.RawInputStream(
        samplerate=capture_rate,
        blocksize=4000,
        device=_parse_device(device),
        dtype="int16",
        channels=1,
        callback=audio_callback,
    ):
        while time.monotonic() < deadline:
            try:
                audio = audio_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            audio_chunks.append(audio)

    print("采集完成，开始识别", file=sys.stderr)
    if not audio_chunks:
        raise TimeoutError("没有采集到有效音频，请检查麦克风和设备号。")

    last_text = ""
    for audio in audio_chunks:
            if recognizer.AcceptWaveform(audio):
                result = json.loads(recognizer.Result())
                text = result.get("text", "")
                if text:
                    last_text = text
                    if verbose:
                        print(f"[asr] {text}", file=sys.stderr)
            else:
                partial = json.loads(recognizer.PartialResult()).get("partial", "")
                if partial:
                    last_text = partial
                    if verbose:
                        print(f"[partial] {partial}", file=sys.stderr)

            color = extract_color_keyword(last_text)
            if color:
                return color, last_text

    final_text = json.loads(recognizer.FinalResult()).get("text", "") or last_text
    color = extract_color_keyword(final_text)
    if color:
        return color, final_text

    raise TimeoutError(f"没有在 {timeout_sec:.1f} 秒内识别到颜色，最后识别文本：{final_text!r}")


def recognize_color_from_audio_file(
    audio_path: str,
    model_path: Optional[str] = None,
    sample_rate: int = 16000,
    verbose: bool = False,
    vosk_runtime: Optional[Tuple[object, object]] = None,
    grammar_json: Optional[str] = None,
) -> Tuple[str, str]:
    """Recognize one audio file and return (english_color, recognized_text)."""
    if vosk_runtime is None:
        KaldiRecognizer, model = load_vosk_runtime(model_path)
    else:
        KaldiRecognizer, model = vosk_runtime
    recognizer = KaldiRecognizer(model, sample_rate, grammar_json) if grammar_json else KaldiRecognizer(model, sample_rate)
    recognizer.SetWords(False)

    command = [
        "ffmpeg",
        "-loglevel",
        "error",
        "-i",
        audio_path,
        "-ac",
        "1",
        "-ar",
        str(sample_rate),
        "-f",
        "s16le",
        "-acodec",
        "pcm_s16le",
        "-",
    ]
    try:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except FileNotFoundError as exc:
        raise RuntimeError("找不到 ffmpeg，请先安装 ffmpeg，或手动转成 16k 单声道 wav。") from exc

    last_text = ""
    assert process.stdout is not None
    while True:
        audio = process.stdout.read(4000)
        if not audio:
            break

        if recognizer.AcceptWaveform(audio):
            text = json.loads(recognizer.Result()).get("text", "")
            if text:
                last_text = text
                if verbose:
                    print(f"[asr] {text}", file=sys.stderr)
                color = extract_color_keyword(text)
                if color:
                    process.kill()
                    process.wait()
                    return color, text
        else:
            partial = json.loads(recognizer.PartialResult()).get("partial", "")
            if partial:
                last_text = partial
                color = extract_color_keyword(partial)
                if color:
                    process.kill()
                    process.wait()
                    return color, partial

    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(f"ffmpeg 解码失败：{stderr.strip()}")

    final_text = json.loads(recognizer.FinalResult()).get("text", "") or last_text
    color = extract_color_keyword(final_text)
    if color:
        return color, final_text

    raise ValueError(f"没有从音频中识别到颜色，识别文本：{final_text!r}")


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="从中文语音中提取颜色，并在终端打印英文颜色名。")
    parser.add_argument("--model", help="Vosk 中文模型目录，例如 ./vosk-model-small-cn-0.22")
    parser.add_argument("--timeout", type=float, default=8.0, help="最长等待秒数，默认 8 秒")
    parser.add_argument("--sample-rate", type=int, default=16000, help="麦克风采样率，默认 16000")
    parser.add_argument("--device", help="sounddevice 麦克风设备编号或名称")
    parser.add_argument("--start-delay", type=float, default=5.0, help="提示后等待多少秒再开始采集，默认 5 秒")
    parser.add_argument("--list-devices", action="store_true", help="列出可用录音设备后退出")
    parser.add_argument("--audio", nargs="+", help="识别一个或多个音频文件，支持 ffmpeg 可读取的格式，例如 .m4a/.wav")
    parser.add_argument("--text", help="不使用麦克风，直接从文本里测试颜色提取")
    parser.add_argument("--show-time", action="store_true", help="打印从开始识别到输出结果的耗时（秒）")
    parser.add_argument("--rounds", type=int, default=1, help="麦克风连续识别轮数，0 表示无限循环")
    parser.add_argument("--no-grammar", action="store_true", help="关闭颜色语法约束（默认开启约束以提升速度）")
    parser.add_argument("--verbose", action="store_true", help="打印识别过程信息")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    if args.text:
        start_time = time.perf_counter()
        color = extract_color_keyword(args.text)
        elapsed_sec = time.perf_counter() - start_time
        print(color or "unknown")
        if args.show_time:
            print(f"[elapsed] {elapsed_sec:.3f}s", file=sys.stderr)
        return 0 if color else 1

    if args.list_devices:
        sd, _, _, _ = _import_audio_libs()
        print(sd.query_devices())
        return 0

    grammar_json = build_grammar_json(not args.no_grammar)

    if args.audio:
        model_load_start = time.perf_counter()
        try:
            vosk_runtime = load_vosk_runtime(args.model)
        except Exception as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return 1
        model_load_elapsed = time.perf_counter() - model_load_start
        if args.show_time:
            print(f"[model_load] {model_load_elapsed:.3f}s", file=sys.stderr)

        ok = True
        multi = len(args.audio) > 1
        for audio_path in args.audio:
            if multi:
                print(f"===== {audio_path} =====", file=sys.stderr)
            start_time = time.perf_counter()
            try:
                color, recognized_text = recognize_color_from_audio_file(
                    audio_path=audio_path,
                    sample_rate=args.sample_rate,
                    verbose=args.verbose,
                    vosk_runtime=vosk_runtime,
                    grammar_json=grammar_json,
                )
            except Exception as exc:
                print(f"[error] {audio_path}: {exc}", file=sys.stderr)
                ok = False
                continue
            elapsed_sec = time.perf_counter() - start_time

            if args.verbose:
                print(f"[text] {recognized_text}", file=sys.stderr)
            print(color)
            if args.show_time:
                print(f"[elapsed] {elapsed_sec:.3f}s", file=sys.stderr)
        return 0 if ok else 1

    model_load_start = time.perf_counter()
    try:
        vosk_runtime = load_vosk_runtime(args.model)
    except Exception as exc:
        print(f"[error] {exc}", file=sys.stderr)
        return 1
    model_load_elapsed = time.perf_counter() - model_load_start
    if args.show_time:
        print(f"[model_load] {model_load_elapsed:.3f}s", file=sys.stderr)

    rounds = args.rounds
    if rounds < 0:
        print("[error] --rounds 不能小于 0", file=sys.stderr)
        return 1

    idx = 0
    while rounds == 0 or idx < rounds:
        idx += 1
        if args.verbose and rounds != 1:
            print(f"[round] {idx}", file=sys.stderr)
        try:
            start_time = time.perf_counter()
            color, recognized_text = recognize_color_from_microphone(
                timeout_sec=args.timeout,
                sample_rate=args.sample_rate,
                device=args.device,
                verbose=args.verbose,
                vosk_runtime=vosk_runtime,
                grammar_json=grammar_json,
                prompt_delay_sec=args.start_delay,
            )
        except TimeoutError as exc:
            if rounds != 1:
                if args.verbose:
                    print(f"[timeout] {exc}", file=sys.stderr)
                continue
            print(f"[error] {exc}", file=sys.stderr)
            return 1
        except Exception as exc:
            print(f"[error] {exc}", file=sys.stderr)
            return 1
        elapsed_sec = time.perf_counter() - start_time

        if args.verbose:
            print(f"[text] {recognized_text}", file=sys.stderr)
        print(color)
        if args.show_time:
            print(f"[elapsed] {elapsed_sec:.3f}s", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
