# Creature Rescue Protocol

`Creature Rescue Protocol` is the final stage of an AI-themed escape room project built for the course `Electronic Science Innovation Experiment III`.

The game runs on an Orange Pi and combines offline speech recognition, custom animal detection, LED-based letter hints, OpenCV visual tracking, and logic-puzzle-driven pan-tilt interaction. Players must recover a sealed color clue, identify an animal sample, decode the answer letter by letter, and finally enter the combined `color + animal` password to complete the rescue.

## Project Overview

This stage is designed as a multimodal rescue mission inside the "GrayCity" AI laboratory. The system does not directly reveal the answer after recognition. Instead, it seals the color clue and the animal identity, then gradually releases the password through physical interaction and logical reasoning.

The full gameplay pipeline is:

1. Speech stage: the player speaks a color clue in Chinese.
2. Vision stage: the system detects the target animal from the camera view.
3. Calibration stage: the player calibrates the red marker on the pan-tilt device.
4. Logic stage: the LED matrix reveals letters one by one while the player solves Boolean logic puzzles and moves the red marker into the correct A/B/C sector.
5. Final verification: the player enters the combined `color + animal` answer.

## Visual Model

The animal recognition module is not a generic API call. It is based on a task-oriented fine-tuning workflow starting from `YOLOv5n` pretrained weights, then exported to `ONNX` for Orange Pi edge inference.

Training data was built from an OpenImages V7 Detection-based animal subset. The detector was optimized for this escape-room scenario, where inference speed, deployment simplicity, and real camera robustness all matter.

Reported performance:

| Metric | Value |
|---|---:|
| Precision | 0.8679 |
| Recall | 0.7318 |
| mAP@0.5 | 0.6785 |
| mAP@0.5:0.95 | 0.5998 |

Tiered real-world evaluation:

| Evaluation | Result |
|---|---:|
| Classification correctness | 88.2% (225/255) |
| Detection hit rate | 93.7% (239/255) |

These results were strong enough for the stage design goal: the system detects most valid targets reliably in practice, while keeping the model light enough for Orange Pi deployment.

## Hardware Structure

- Orange Pi as the main controller
- USB microphone for offline speech recognition
- USB camera for animal detection and red-marker tracking
- Independent pan-tilt controller with a red block marker
- 8x8 WS2812 LED matrix for letter display
- External 5V supply for the LED matrix

The pan-tilt device is not directly driven by the Orange Pi. The player moves it manually through an independent controller, and the Orange Pi only judges the marker position from the camera image.

## Core Software Components

- `creature_rescue_game.py`: main GUI and stage state machine
- `speech_color.py`: offline Chinese color recognition using Vosk
- `ws2812_letters_spi.py`: SPI-driven WS2812 letter display
- `detect_animals17_triggered.py`: ONNX-based animal detector
- `model_artifacts/deploy_pack_20260507/animals17_best.onnx`: deployed detector
- `model_artifacts/deploy_pack_20260507/labels.txt`: detector labels

## Repository Layout

```text
.
|-- creature_rescue_game.py
|-- speech_color.py
|-- ws2812_letters_spi.py
|-- detect_animals17_triggered.py
|-- requirements.txt
|-- run_multimodal_orangepi.sh
`-- model_artifacts/
    `-- deploy_pack_20260507/
        |-- animals17_best.onnx
        `-- labels.txt
```

## Setup

Install Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

The Vosk Chinese model is not included in this repository. Download and extract `vosk-model-small-cn-0.22` separately, then pass its path with `--vosk-model`.

Typical system packages on Orange Pi:

```bash
sudo apt update
sudo apt install -y python3-tk ffmpeg libportaudio2 libportaudio-dev python3-spidev
```

## Run

```bash
python3 creature_rescue_game.py \
  --vosk-model ./vosk-model-small-cn-0.22 \
  --yolo-model model_artifacts/deploy_pack_20260507/animals17_best.onnx \
  --yolo-labels model_artifacts/deploy_pack_20260507/labels.txt
```

Or use the helper script:

```bash
bash run_multimodal_orangepi.sh
```

Optional runtime arguments:

- `--device /dev/video1` to force a camera device
- `--audio-device "hw:3"` to force a microphone device
- `--window-width` / `--window-height` for remote desktop layouts

## Notes

- The game auto-detects usable camera and microphone devices when possible.
- The GUI intentionally hides the recognized color and animal after the recognition stages.
- The final answer format is `color + animal`, for example `green zebra`.
- LED power must come from an external 5V source, not directly from GPIO power.
