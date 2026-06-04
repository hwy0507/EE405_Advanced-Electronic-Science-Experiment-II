# Animal Demo（Orange Pi Zero 3）

这个 Demo 用于验证你们关卡中的“动物图像 -> 英文动物词”能力。

## 1. 从 Mac 传到香橙派

在 **Mac 终端** 执行：

```bash
scp -r /Users/hwy/Documents/dianchuang/animal_demo orangepi@opi-zero3.local:~/
```

如果 `.local` 不稳定，改为 IP：

```bash
scp -r /Users/hwy/Documents/dianchuang/animal_demo orangepi@10.28.233.11:~/
```

## 2. 在香橙派安装依赖

```bash
ssh orangepi@opi-zero3.local
cd ~/animal_demo

sudo apt update
sudo apt install -y python3-pip python3-venv python3-opencv

python3 -m venv --system-site-packages .venv
source .venv/bin/activate
pip install -U pip
pip install -r requirements.txt
```

## 3. 运行方式

### A) 用现成图片测试

```bash
source ~/animal_demo/.venv/bin/activate
cd ~/animal_demo
python classify_animal.py --image /path/to/animal.jpg
```

### B) 直接调用 USB 摄像头拍一张再识别

```bash
source ~/animal_demo/.venv/bin/activate
cd ~/animal_demo
python classify_animal.py --capture --device /dev/video1 --save-capture shot.jpg
```

如果 `/dev/video1` 不通，可以试 `/dev/video2`。

## 4. 输出说明

- `TOP-K`：模型最可能的类别
- `animal_word`：映射后的英文动物词（用于你们后续 LED 字母解锁流程）

例如：

```text
[RESULT] animal_word = panda
```

## 5. 代码集成建议

你们主程序里可以把这个结果作为关卡的“动物代号”输入：

```python
animal_word = "panda"  # 由 classify_animal.py 得到
```

然后进入你们的颜色密钥和摇杆逻辑门流程。
