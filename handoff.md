# GitHub 上传指南

## 目的

将「生灵解救协议」多模态游戏项目整理并上传到 GitHub。

---

## 保留的文件

### 核心代码（必须）

| 文件 | 说明 |
|------|------|
| `creature_rescue_game.py` | 主游戏程序（当前最新版本） |
| `speech_color.py` | 语音颜色识别模块 |
| `ws2812_letters_spi.py` | LED灯板控制模块 |
| `abc_red_zone_test.py` | ABC扇形追踪测试程序 |
| `led_zebra_test.py` | LED测试脚本 |
| `run_multimodal_orangepi.sh` | 启动脚本 |

### 模型文件（必须）

| 文件/目录 | 说明 |
|----------|------|
| `model_artifacts/deploy_pack_20260507/` | 整个目录保留 |
| `model_artifacts/deploy_pack_20260507/animals17_best.onnx` | 动物识别模型 |
| `model_artifacts/deploy_pack_20260507/labels.txt` | 动物类别标签 |

### 文档（必须）

| 文件 | 说明 |
|------|------|
| `README.md` | 项目说明文档 |
| `handoff.md` | 本文件 |

---

## 删除的文件

### 旧版本/废弃代码

```bash
# 删除这些旧版本GUI（已被 creature_rescue_game.py 替代）
rm multimodal_game_gui.py
rm multimodal_rescue_gui.py
rm multimodal_rescue_gui_orangepi.py

# 删除废弃的stub文件
rm vision_animal.py
rm logic_gate.py
rm main_demo.py

# 删除word文档生成工具（课程资料，非必需）
rm make_*.py
```

### animal_demo 目录（可选删除）

```bash
# 这个目录下有大量实验性文件，已被整合到 creature_rescue_game.py
# 如果要保留，只保留核心文件：
# - detect_animals17_triggered.py（被主程序引用）
# - requirements.txt（依赖清单）
# - README_zh.md（中文说明）

# 删除其他实验文件
cd animal_demo
rm animal_api_*.py
rm animal_yolo_api_hybrid.py
rm classify_animal.py
rm detect_animal_live_v8.py
rm detect_animal_triggered_yolo.py
cd ..
```

### 其他清理

```bash
# 删除训练包（课程资料，非运行时必需）
rm -rf train_yolo_animals_pkg/

# 删除VSCode配置（不需要）
rm -rf .vscode/

# 删除samples样本数据
rm -rf samples_animals17_3each/
```

---

## 目录结构（清理后）

```
dianchuang/
├── README.md                      # 项目说明
├── handoff.md                     # 本文件（上传后可删除）
├── creature_rescue_game.py        # 主游戏程序
├── speech_color.py               # 语音识别模块
├── ws2812_letters_spi.py         # LED控制模块
├── abc_red_zone_test.py           # 扇形追踪测试
├── led_zebra_test.py             # LED测试脚本
├── run_multimodal_orangepi.sh     # 启动脚本
│
├── animal_demo/
│   ├── detect_animals17_triggered.py  # 动物识别核心
│   ├── requirements.txt              # Python依赖
│   └── README_zh.md                 # 中文说明
│
└── model_artifacts/
    └── deploy_pack_20260507/
        ├── animals17_best.onnx      # 动物识别模型（7.5MB）
        └── labels.txt               # 标签文件
```

---

## .gitignore 文件

在仓库根目录创建 `.gitignore`：

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/

# 模型文件（大文件，使用Git LFS）
# model_artifacts/deploy_pack_20260507/animals17_best.onnx

# 临时文件
*.swp
*.swo
*~
.DS_Store

# 编译产物
*.so
*.c

# 本地配置
.env
*.local
```

**注意**：`animals17_best.onnx` 模型文件约7.5MB，可以直接提交，或者使用 Git LFS：

```bash
# 安装 Git LFS
git lfs install

# 追踪大文件
git lfs track "*.onnx"
git add .gitattributes
```

---

## 上传步骤

### 1. 初始化仓库

```bash
cd dianchuang

git init

# 配置用户（如果不是全局配置）
git config user.name "Your Name"
git config user.email "your@email.com"
```

### 2. 添加文件

```bash
git add .
git status  # 检查添加的文件
```

### 3. 提交

```bash
git commit -m "Initial commit: 生灵解救协议多模态游戏"
```

### 4. 创建 GitHub 仓库

在 GitHub 网页创建新仓库，获得仓库地址如：
`https://github.com/username/dianchuang.git`

### 5. 推送到 GitHub

```bash
git remote add origin https://github.com/username/dianchuang.git
git branch -M main
git push -u origin main
```

---

## 注意事项

1. **模型文件**：`animals17_best.onnx` 约7.5MB，普通git可以处理，但建议确认仓库大小限制
2. **Vosk模型**：约45MB，**不要**上传到GitHub，需用户自行下载
3. **敏感信息**：确保代码中没有硬编码的密码或密钥
4. **LICENSE**：建议添加 MIT 或 Apache 2.0 许可证

---

## 后续agent操作提示

1. 先运行清理命令删除废弃文件
2. 确认目录结构符合上述要求
3. 创建 `.gitignore`
4. 按步骤初始化并推送
5. 上传完成后删除 `handoff.md`（可选）

---

最后更新：2026-06-03