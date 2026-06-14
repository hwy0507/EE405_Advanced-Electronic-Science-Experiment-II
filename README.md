# 生灵解救协议 - 多模态交互游戏

## 项目概述

这是一个运行在香橙派（Orange Pi）上的多模态交互游戏，玩家通过语音、视觉和物理操控三位一体来解救被困的生灵。

**控制架构说明**：
- 香橙派作为主控，运行游戏GUI和AI识别
- 云台由**独立控制板**操控（如游戏手柄、摇杆），**不直接连接香橙派**
- 香橙派仅通过摄像头视觉追踪云台上的红色方块位置
- 玩家手动操控云台，将红色方块移动到屏幕上的正确扇形区域

### 游戏流程

```
┌─────────────────────────────────────────────────────────────────┐
│                        游戏流程图                                │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  第1关：语音识别                                                   │
│  ├── 玩家对着麦克风说："我选择的颜色是XX"                          │
│  └── 系统识别颜色并封存线索，后续界面不直接显示答案                  │
│                           ↓                                       │
│  第2关：动物识别                                                   │
│  ├── 摄像头显示画面                                                │
│  ├── 玩家将动物照片对着摄像头，点击"识别此画面"                      │
│  └── 系统识别动物并封存身份，后续通过LED逐字解锁最终密码              │
│                           ↓                                       │
│  第3关：云台标定                                                   │
│  ├── 玩家通过控制板操控云台，将红色方块移到画面中央                   │
│  ├── 点击"标定此位置"                                              │
│  └── 系统自动划分ABC扇形，并选择简单/普通/困难难度                   │
│                           ↓                                       │
│  第4关：游戏闯关                                                   │
│  ├── LED显示单词第1个字母                                          │
│  ├── 屏幕显示逻辑题（玩家需操控云台进入正确扇形）                    │
│  ├── 扇形按当前难度的初始大小和速度逐渐缩小                          │
│  ├── 玩家操控云台移动后点击"确认位置"检查答案                       │
│  ├── 答对 → LED显示下一个字母，重复                                 │
│  └── 所有字母完成 → 输入颜色+动物名最终答案通关                      │
│                                                                  │
│  ★ 云台由独立控制板操控，香橙派仅通过摄像头追踪红色位置 ★            │
└─────────────────────────────────────────────────────────────────┘
```

### 硬件组成

| 设备 | 说明 |
|------|------|
| 香橙派 Orange Pi 5/Zero 3 | 主控板，运行Debian系统，通过USB连接摄像头和麦克风 |
| USB摄像头 | 用于动物识别（如Logitech C270） |
| USB麦克风 | 用于语音识别颜色 |
| 云台+红色方块 | **独立控制板操控**，香橙派仅通过摄像头视觉追踪红色位置 |
| WS2812 LED灯板 8x8 | 通过香橙派SPI接口控制，显示字母和颜色主题 |

---

## 硬件接线

### 1. LED灯板接线（WS2812 8x8矩阵）

```
┌────────────────────────────────────────────────────────────┐
│                     WS2812 LED灯板                         │
│                                                            │
│   DIN (数据输入) ──────────► 香橙派 PH7 (SPI1_MOSI)         │
│   GND (地线)      ──────────► 香橙派 GND                  │
│   5V (电源)       ──────────► 外部5V电源（不要从GPIO取电！）│
│                                                            │
└────────────────────────────────────────────────────────────┘
```

| LED面板 | 香橙派 Orange Pi |
|---------|------------------|
| DIN (数据输入) | PH7 (SPI1_MOSI) |
| GND | GND（任意地线引脚） |
| 5V | **外部5V电源**（必须！GPIO无法提供足够电流） |

**重要提示**：
- LED灯板需要外部5V电源供电，**禁止从香橙派GPIO取电**
- LED工作电流可达数安培，从GPIO取电会损坏香橙派
- GND必须与香橙派共地（连接在一起）

### 2. 云台控制（独立控制，不连接香橙派）

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   玩家手持云台控制杆                                         │
│        ↓                                                    │
│   云台控制板（独立控制，不连接香橙派）                          │
│        ↓                                                    │
│   云台上的红色方块随控制移动                                  │
│        ↓                                                    │
│   香橙派摄像头追踪红色方块位置                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**控制方式**：
- 云台由**独立控制板**控制（如游戏手柄、摇杆等）
- 香橙派**不直接控制云台**，只通过摄像头视觉追踪红色方块
- 玩家手动操控云台移动红色方块到屏幕上的ABC扇形区域

### 3. 摄像头和麦克风

```
┌─────────────────────────────────────────────────────────────┐
│                                                             │
│   USB摄像头 ──────────► 香橙派 USB接口                       │
│   USB麦克风  ──────────► 香橙派 USB接口                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

这两个设备即插即用，通过USB连接即可。

---

## 设备检测

### 1. 检测摄像头设备

```bash
# 查看所有视频设备
ls -la /dev/video*

# 测试摄像头是否正常工作
# 方法1：安装fswebcam拍照测试
sudo apt install fswebcam
fswebcam --no-overlay -r 640x480 /tmp/test.jpg

# 方法2：用Python OpenCV测试
python3 -c "
import cv2
cap = cv2.VideoCapture('/dev/video1')
ok, frame = cap.read()
cap.release()
print('摄像头正常' if ok else '摄像头失败')
"
```

### 2. 检测麦克风设备

```bash
# 查看所有音频设备
arecord -l

# 或者
cat /proc/asound/cards

# 测试录音
arecord -d 5 -D plughw:3 -f cd /tmp/test.wav
aplay /tmp/test.wav  # 播放录音测试是否正常
```

### 3. 查看设备号

```bash
# 摄像头设备号
# /dev/video0 - 板载MIPI摄像头
# /dev/video1 - USB摄像头（通常用这个）
# /dev/video2 - 备用

# 麦克风设备号
# hw:0, hw:1, hw:2 - HDMI音频（通常不用）
# hw:3 - USB麦克风（常用）

# 列出详细设备信息
pactl list sources short
```

---

## 安装依赖

### 1. 系统依赖

```bash
sudo apt update
sudo apt install -y python3-pip python3-picamera python3-pil
sudo apt install -y libportaudio2 libportaudio-dev
sudo apt install -y ffmpeg
```

### 2. Python依赖

```bash
pip3 install opencv-python onnxruntime sounddevice pillow numpy --break-system-packages
```

### 3. 下载Vosk中文模型

```bash
cd ~/20260603
wget https://alphacephei.com/vosk/models/vosk-model-small-cn-0.22.zip
unzip vosk-model-small-cn-0.22.zip
```

---

## 运行游戏

### 启动命令

```bash
cd ~/20260603

python3 creature_rescue_game.py \
  --vosk-model ./vosk-model-small-cn-0.22 \
  --yolo-model model_artifacts/deploy_pack_20260507/animals17_best.onnx \
  --yolo-labels model_artifacts/deploy_pack_20260507/labels.txt \
  --yolo-conf 0.35
```

程序默认会自动搜索摄像头和麦克风：摄像头必须能成功读出画面，麦克风必须能成功打开输入流。启动页会显示最终选择的设备。

如果需要手动指定设备，可以追加参数：

```bash
python3 creature_rescue_game.py --device /dev/video1 --audio-device "hw:3"
```

如果在 NoMachine 里看不到底部按钮，可以调小窗口高度：

```bash
python3 creature_rescue_game.py --window-width 1024 --window-height 650
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--device` | auto | 摄像头设备号；默认自动探测 |
| `--audio-device` | auto | 麦克风输入设备；默认自动探测 |
| `--vosk-model` | ./vosk-model-small-cn-0.22 | Vosk模型路径 |
| `--width` | 640 | 摄像头分辨率宽度 |
| `--height` | 480 | 摄像头分辨率高度 |
| `--window-width` | 1180 | 程序窗口宽度 |
| `--window-height` | 720 | 程序窗口高度 |

### 启动脚本

也可以直接运行启动脚本：

```bash
bash run_multimodal_orangepi.sh
```

---

## 各模块测试

### 1. 测试语音识别

```bash
# 录音识别
python3 speech_color.py --device "hw:3" --model ./vosk-model-small-cn-0.22 --timeout 10
# 对着麦克风说："我选择的颜色是蓝色"
# 应该输出：blue
```

### 2. 测试动物识别

```bash
# 单次识别
python3 -c "
from pathlib import Path
from animal_demo.detect_animals17_triggered import YoloDetector
import cv2

detector = YoloDetector(
    model_path=Path('model_artifacts/deploy_pack_20260507/animals17_best.onnx'),
    labels_path=Path('model_artifacts/deploy_pack_20260507/labels.txt'),
    conf_thres=0.35,
    iou_thres=0.45,
    det_size=640,
    threads=2,
    ort_opt='basic'
)

cap = cv2.VideoCapture('/dev/video1')
ok, frame = cap.read()
cap.release()

if ok:
    det = detector.detect_best(frame, None)
    print(f'识别: {det.label} 置信度: {det.conf:.2f}' if det else '未识别到动物')
"
```

### 3. 测试LED灯板

```bash
# 显示单个字母
python3 ws2812_letters_spi.py --text "A" --color green --layout col --rotate 0 --flip-x
# 如果提示没有权限，再使用：
sudo python3 ws2812_letters_spi.py --text "A" --color green --layout col --rotate 0 --flip-x

# 显示ZEBRA
for letter in Z E B R A; do
  python3 ws2812_letters_spi.py --text "$letter" --color green --layout col --rotate 0 --flip-x
  sleep 2
done

# 关灯
python3 ws2812_letters_spi.py --text " " --color "#000000"
```

### 4. 测试ABC扇形追踪

```bash
# 运行红色方块追踪测试
python3 abc_red_zone_test.py --device /dev/video1 --auto-calib

# 按 c 键标定，按 p 输出当前扇形，按 q 退出
```

---

## 文件结构

```
~/20260603/
├── creature_rescue_game.py     # 主游戏程序
├── speech_color.py              # 语音颜色识别模块
├── ws2812_letters_spi.py        # LED灯板控制模块
├── abc_red_zone_test.py         # ABC扇形追踪测试
├── run_multimodal_orangepi.sh   # 启动脚本
│
├── animal_demo/
│   ├── detect_animals17_triggered.py  # YOLO动物识别
│   └── ...（其他动物识别相关文件）
│
├── model_artifacts/
│   └── deploy_pack_20260507/
│       ├── animals17_best.onnx   # 动物识别模型
│       └── labels.txt            # 动物类别标签
│
└── vosk-model-small-cn-0.22/    # 中文语音识别模型
```

---

## 常见问题

### Q1: 摄像头打不开
```bash
# 查看程序启动页自动选择的摄像头，必要时手动指定
ls -la /dev/video*
python3 creature_rescue_game.py --device /dev/video0

# 如果没有权限，添加用户组
sudo usermod -a -G video orangepi
# 然后重新登录
```

### Q2: 语音识别失败
```bash
# 查看程序启动页自动选择的麦克风，必要时手动指定
arecord -l
python3 creature_rescue_game.py --audio-device "hw:3"

# 确认模型文件存在
ls -la vosk-model-small-cn-0.22/

# 测试麦克风能否录音
arecord -d 3 -D plughw:3 -f cd /tmp/test.wav
```

### Q3: LED灯板不亮
```bash
# 检查SPI设备
ls -la /dev/spidev*

# 主程序会在状态栏显示LED错误。若提示Permission denied，说明SPI没有权限：
sudo chmod 666 /dev/spidev1.0

# sudo -n 不会弹出密码输入；若提示需要密码，说明主程序不能自动提权
sudo -n python3 ws2812_letters_spi.py --text "A" --color green --layout col --rotate 0 --flip-x

# 检查接线（DIN接PH7/GND共地/5V外接电源）
```

### Q4: 动物识别一直失败
```bash
# 检查模型文件是否存在
ls -la model_artifacts/deploy_pack_20260507/animals17_best.onnx

# 检查置信度是否太高，降低阈值
--yolo-conf 0.25

# 确保摄像头对着动物照片，背景尽量干净
```

### Q5: 扇形追踪不准
```bash
# 重新标定，确保红色方块在画面中央
# 如果红色检测不到，检查：
# 1. 光照是否足够
# 2. 红色方块是否够大（面积>200像素）
# 3. 背景是否有其他红色物体干扰
```

---

## 逻辑题说明

游戏中的逻辑题格式示例：

```
A AND B = 0
A OR C = 1
B AND C = 1

Which equals 0?
```

根据方程推断，`B AND C = 1` 可知 `B=1, C=1`；再由 `A AND B = 0` 可知 `A=0`。所以正确答案进入A扇形。

题目库包含18道题，覆盖 `A=0`、`A=1`、`B=0`、`B=1`、`C=0`、`C=1` 六种目标，每种目标3道题。程序启动时会自动验证题库：每道题在 `A/B/C` 的8种取值中只有一个完整解，并且题目询问的目标值只对应一个正确扇形。

进入游戏关卡前，玩家可选择难度：简单、普通、困难分别对应不同的初始扇形大小和缩减速度。进入游戏关卡后，系统会从18道题中随机抽题；玩家点击「锁定并判定」后，程序会用当前摄像头画面重新检测红色方块所在扇形。答对后进入下一题，并且下一题只会从本局尚未出现过的题目中随机选择。

---

## 注意事项

1. **LED需要单独供电** - 不要从GPIO取电，会烧坏香橙派
2. **摄像头和麦克风都要测试** - 不同设备号可能不同
3. **Vosk模型只需下载一次** - 约45MB
4. **游戏过程中不要关闭程序** - 会导致LED无法关闭

---

## 联系和调试

如果遇到问题，按以下顺序排查：

1. 先单独测试每个模块（摄像头/麦克风/LED）
2. 检查设备号是否正确
3. 查看错误信息，定位问题
4. 必要时重启香橙派

---

最后更新：2026-06-04
