#!/usr/bin/env python3
"""
LED 测试脚本：显示 ZEBRA，每个字母2.5秒，结束后自动关灯
配置：--layout col --rotate 0 --flip-x
"""
import subprocess
import time
import sys

LETTERS = "ZEBRA"
COLOR = "green"
BRIGHTNESS = 0.3
INTERVAL = 2.5  # 每个字母显示时间（秒）


def show_letter(letter):
    """显示单个字母"""
    cmd = [
        "sudo", "python3", "ws2812_letters_spi.py",
        "--text", letter,
        "--color", COLOR,
        "--brightness", str(BRIGHTNESS),
        "--layout", "col",
        "--rotate", "0",
        "--flip-x",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  警告: {result.stderr}", file=sys.stderr)


def clear_led():
    """关灯（显示全黑）"""
    cmd = [
        "sudo", "python3", "ws2812_letters_spi.py",
        "--text", " ",
        "--color", "#000000",
    ]
    subprocess.run(cmd)


def main():
    print(f"[LED] 开始显示: {LETTERS}")
    print(f"[LED] 配置: layout=col, rotate=0, flip-x=True, color={COLOR}, brightness={BRIGHTNESS}")

    for letter in LETTERS:
        print(f"[LED] 显示: {letter}")
        show_letter(letter)
        time.sleep(INTERVAL)

    print("[LED] 显示完成，关灯...")
    clear_led()
    print("[LED] 完成！LED已关闭")


if __name__ == "__main__":
    main()