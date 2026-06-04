#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "[INFO] Working dir: $(pwd)"

if [ ! -f "multimodal_rescue_gui_orangepi.py" ]; then
  echo "[ERROR] missing multimodal_rescue_gui_orangepi.py"
  exit 1
fi

if [ ! -f "speech_color.py" ]; then
  echo "[ERROR] missing speech_color.py"
  exit 1
fi

MODEL_DEFAULT=""
LABELS_DEFAULT=""

if [ -f "$HOME/animal_yolo_demo/models/animals17_best.onnx" ] && [ -f "$HOME/animal_yolo_demo/models/labels.txt" ]; then
  MODEL_DEFAULT="$HOME/animal_yolo_demo/models/animals17_best.onnx"
  LABELS_DEFAULT="$HOME/animal_yolo_demo/models/labels.txt"
elif [ -f "$HOME/animal_demo/models/animals17_best.onnx" ] && [ -f "$HOME/animal_demo/models/labels.txt" ]; then
  MODEL_DEFAULT="$HOME/animal_demo/models/animals17_best.onnx"
  LABELS_DEFAULT="$HOME/animal_demo/models/labels.txt"
else
  MODEL_DEFAULT="$HOME/animals17_release_latest/models/animals17_best.onnx"
  LABELS_DEFAULT="$HOME/animals17_release_latest/models/labels.txt"
fi

if [ ! -f "$MODEL_DEFAULT" ]; then
  echo "[WARN] default model not found: $MODEL_DEFAULT"
  echo "       pass --yolo-model manually"
fi
if [ ! -f "$LABELS_DEFAULT" ]; then
  echo "[WARN] default labels not found: $LABELS_DEFAULT"
  echo "       pass --yolo-labels manually"
fi

python3 multimodal_rescue_gui_orangepi.py \
  --device /dev/video0 \
  --yolo-model "$MODEL_DEFAULT" \
  --yolo-labels "$LABELS_DEFAULT" \
  "$@"
