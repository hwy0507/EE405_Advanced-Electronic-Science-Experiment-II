#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo "[INFO] Working dir: $(pwd)"

if [ ! -f "creature_rescue_game.py" ]; then
  echo "[ERROR] missing creature_rescue_game.py"
  exit 1
fi

if [ ! -f "speech_color.py" ]; then
  echo "[ERROR] missing speech_color.py"
  exit 1
fi

MODEL_DEFAULT="model_artifacts/deploy_pack_20260507/animals17_best.onnx"
LABELS_DEFAULT="model_artifacts/deploy_pack_20260507/labels.txt"

if [ -f "$MODEL_DEFAULT" ] && [ -f "$LABELS_DEFAULT" ]; then
  :
elif [ -f "$HOME/animal_yolo_demo/models/animals17_best.onnx" ] && [ -f "$HOME/animal_yolo_demo/models/labels.txt" ]; then
  MODEL_DEFAULT="$HOME/animal_yolo_demo/models/animals17_best.onnx"
  LABELS_DEFAULT="$HOME/animal_yolo_demo/models/labels.txt"
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

python3 creature_rescue_game.py \
  --yolo-model "$MODEL_DEFAULT" \
  --yolo-labels "$LABELS_DEFAULT" \
  "$@"
