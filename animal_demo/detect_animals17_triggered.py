#!/usr/bin/env python3
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import cv2
import numpy as np
import onnxruntime as ort


@dataclass
class DetResult:
    label: str
    conf: float
    box: Tuple[int, int, int, int]  # x1, y1, x2, y2


def load_names(path: Path) -> List[str]:
    names = [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
    if not names:
        raise RuntimeError(f"Invalid labels file: {path}")
    return names


def letterbox(img: np.ndarray, new_h: int, new_w: int) -> Tuple[np.ndarray, float, float, float]:
    h0, w0 = img.shape[:2]
    r = min(new_w / w0, new_h / h0)

    wn = int(round(w0 * r))
    hn = int(round(h0 * r))
    resized = cv2.resize(img, (wn, hn), interpolation=cv2.INTER_LINEAR)

    dw = (new_w - wn) / 2.0
    dh = (new_h - hn) / 2.0

    top = int(round(dh - 0.1))
    bottom = int(round(dh + 0.1))
    left = int(round(dw - 0.1))
    right = int(round(dw + 0.1))

    padded = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=(114, 114, 114))
    return padded, r, dw, dh


def preprocess(img_bgr: np.ndarray, in_h: int, in_w: int) -> Tuple[np.ndarray, float, float, float]:
    lb, r, dw, dh = letterbox(img_bgr, in_h, in_w)
    rgb = cv2.cvtColor(lb, cv2.COLOR_BGR2RGB)
    x = rgb.astype(np.float32) / 255.0
    x = np.transpose(x, (2, 0, 1))[None]
    return x, r, dw, dh


def expand_box(box: Tuple[int, int, int, int], frame_w: int, frame_h: int, scale: float) -> Tuple[int, int, int, int]:
    x1, y1, x2, y2 = box
    bw = max(1, x2 - x1)
    bh = max(1, y2 - y1)
    cx = (x1 + x2) / 2.0
    cy = (y1 + y2) / 2.0

    nw = bw * scale
    nh = bh * scale

    nx1 = int(max(0, round(cx - nw / 2)))
    ny1 = int(max(0, round(cy - nh / 2)))
    nx2 = int(min(frame_w - 1, round(cx + nw / 2)))
    ny2 = int(min(frame_h - 1, round(cy + nh / 2)))

    if nx2 <= nx1:
        nx2 = min(frame_w - 1, nx1 + 1)
    if ny2 <= ny1:
        ny2 = min(frame_h - 1, ny1 + 1)

    return nx1, ny1, nx2, ny2


class YoloDetector:
    def __init__(
        self,
        model_path: Path,
        labels_path: Path,
        conf_thres: float,
        iou_thres: float,
        det_size: int,
        threads: int,
        ort_opt: str,
    ) -> None:
        self.names = load_names(labels_path)
        self.allowed = {x.lower() for x in self.names}
        self.conf_thres = conf_thres
        self.iou_thres = iou_thres

        so = ort.SessionOptions()
        so.intra_op_num_threads = max(1, threads)
        so.inter_op_num_threads = 1
        if ort_opt == "disable":
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        elif ort_opt == "basic":
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_BASIC
        else:
            so.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        self.sess = ort.InferenceSession(str(model_path), sess_options=so, providers=["CPUExecutionProvider"])
        self.input_name = self.sess.get_inputs()[0].name
        shape = self.sess.get_inputs()[0].shape

        self.in_h = det_size
        self.in_w = det_size
        if (
            isinstance(shape, (list, tuple))
            and len(shape) >= 4
            and isinstance(shape[2], int)
            and isinstance(shape[3], int)
            and shape[2] > 0
            and shape[3] > 0
        ):
            self.in_h = int(shape[2])
            self.in_w = int(shape[3])

    def detect_best(self, frame: np.ndarray, roi: Optional[Tuple[int, int, int, int]] = None) -> Optional[DetResult]:
        if roi is not None:
            rx1, ry1, rx2, ry2 = roi
            sub = frame[ry1:ry2, rx1:rx2]
            ox, oy = rx1, ry1
        else:
            sub = frame
            ox, oy = 0, 0

        if sub.size == 0:
            return None

        input_tensor, r, dw, dh = preprocess(sub, self.in_h, self.in_w)
        out = self.sess.run(None, {self.input_name: input_tensor})[0]

        if out.ndim != 3:
            return None

        preds = out[0] if out.shape[1] >= out.shape[2] else out[0].T

        sh, sw = sub.shape[:2]
        boxes_xywh: List[List[int]] = []
        scores: List[float] = []
        class_ids: List[int] = []

        ncol = preds.shape[1]
        # YOLOv5 ONNX: [x,y,w,h,obj,cls1...]
        has_obj = (ncol == len(self.names) + 5) or (ncol >= 85)

        for row in preds:
            if has_obj:
                obj = float(row[4])
                cls_scores = row[5:]
            else:
                obj = 1.0
                cls_scores = row[4:]

            if cls_scores.size == 0:
                continue

            cid = int(np.argmax(cls_scores))
            cls_conf = float(cls_scores[cid])
            conf = obj * cls_conf

            if conf < self.conf_thres:
                continue
            if cid >= len(self.names):
                continue

            label = self.names[cid].lower()
            if label not in self.allowed:
                continue

            xc, yc, w, h = row[:4]
            x1m = xc - w / 2.0
            y1m = yc - h / 2.0
            x2m = xc + w / 2.0
            y2m = yc + h / 2.0

            x1 = int(max(0, min(sw - 1, round((x1m - dw) / r))))
            y1 = int(max(0, min(sh - 1, round((y1m - dh) / r))))
            x2 = int(max(0, min(sw - 1, round((x2m - dw) / r))))
            y2 = int(max(0, min(sh - 1, round((y2m - dh) / r))))

            ww = max(1, x2 - x1)
            hh = max(1, y2 - y1)

            boxes_xywh.append([x1, y1, ww, hh])
            scores.append(conf)
            class_ids.append(cid)

        if not boxes_xywh:
            return None

        idxs = cv2.dnn.NMSBoxes(boxes_xywh, scores, self.conf_thres, self.iou_thres)
        if idxs is None or len(idxs) == 0:
            return None

        keep = np.array(idxs).reshape(-1)
        best_idx = max(keep.tolist(), key=lambda i: scores[int(i)])

        x1, y1, w, h = boxes_xywh[int(best_idx)]
        x2, y2 = x1 + w, y1 + h
        conf = float(scores[int(best_idx)])
        label = self.names[class_ids[int(best_idx)]]

        return DetResult(label=label, conf=conf, box=(x1 + ox, y1 + oy, x2 + ox, y2 + oy))


def main() -> None:
    ap = argparse.ArgumentParser(description="Animals17 live recognition (YOLOv5 ONNX, one-shot on key press)")
    ap.add_argument("--device", default="/dev/video0")
    ap.add_argument("--model", default="models/animals17_best.onnx")
    ap.add_argument("--labels", default="models/labels.txt")
    ap.add_argument("--width", type=int, default=320)
    ap.add_argument("--height", type=int, default=240)
    ap.add_argument("--mjpg", action="store_true")
    ap.add_argument("--det-size", type=int, default=320)
    ap.add_argument("--det-conf", type=float, default=0.35)
    ap.add_argument("--iou", type=float, default=0.45)
    ap.add_argument("--threads", type=int, default=2)
    ap.add_argument("--ort-opt", choices=["disable", "basic", "all"], default="basic")
    ap.add_argument("--camera-fps", type=int, default=30)
    ap.add_argument("--buffer-size", type=int, default=1, help="V4L2 buffer size; smaller = lower latency")
    ap.add_argument("--drop-old-frames", type=int, default=1, help="Drop queued stale frames before read")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--detect-key", default="p", help="Press this key to detect current frame once")
    args = ap.parse_args()

    model_path = Path(args.model)
    labels_path = Path(args.labels)
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not labels_path.exists():
        raise FileNotFoundError(f"Labels not found: {labels_path}")

    detector = YoloDetector(
        model_path=model_path,
        labels_path=labels_path,
        conf_thres=args.det_conf,
        iou_thres=args.iou,
        det_size=args.det_size,
        threads=args.threads,
        ort_opt=args.ort_opt,
    )

    cap = cv2.VideoCapture(args.device, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open camera: {args.device}")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)
    cap.set(cv2.CAP_PROP_FPS, args.camera_fps)
    cap.set(cv2.CAP_PROP_BUFFERSIZE, max(1, args.buffer_size))
    if args.mjpg:
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

    show_enabled = bool(args.show)
    detect_key = ord(args.detect_key[0]) if args.detect_key else ord("p")
    frame_idx = 0

    # Keep last one-shot result for overlay.
    last_det: Optional[DetResult] = None

    print(f"[INFO] Ready. keys: {chr(detect_key)}=detect current frame once, q=quit")

    while True:
        for _ in range(max(0, args.drop_old_frames)):
            cap.grab()
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.01)
            continue

        frame_idx += 1
        if show_enabled:
            cv2.putText(
                frame,
                f"Press '{chr(detect_key)}' to detect this frame once",
                (8, 22),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 255),
                2,
            )

        if show_enabled and last_det is not None:
            x1, y1, x2, y2 = last_det.box
            cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 200, 255), 2)
            cv2.putText(frame, f"{last_det.label} {last_det.conf:.2f}", (x1, max(15, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 200, 255), 2)

        if show_enabled:
            cv2.imshow("animals17_live", frame)
            key = cv2.waitKey(1) & 0xFF
        else:
            key = -1
            time.sleep(0.001)

        if key == ord("q"):
            break
        if key == detect_key:
            t0 = time.time()
            # detect_best already returns the highest-confidence target among all detections
            det = detector.detect_best(frame, None)
            dt_ms = (time.time() - t0) * 1000.0
            if det is None:
                last_det = None
                print(f"[RESULT] none ({dt_ms:.1f} ms)")
            else:
                last_det = det
                print(f"[RESULT] {det.label.lower()} conf={det.conf:.3f} ({dt_ms:.1f} ms)")

    cap.release()
    if show_enabled:
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
