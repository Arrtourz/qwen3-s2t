# s2t — Ubuntu 语音输入工具

类 Win+H / MySuperWhisper，基于 Qwen3-ASR-1.7B，全局热键触发，转写后自动粘贴。

## 功能

- **持续模式**（默认）：第一次双击 Ctrl 开启麦克风持续监听，此后每次双击截取并转写上一段语音
- **手动模式**（`--manual`）：双击 Ctrl 开始录音，再次双击停止并转写
- 长按 Ctrl 2 秒：退出程序
- 智能粘贴：自动检测终端（Ctrl+Shift+V）vs 普通窗口（Ctrl+V），多行文本逐行粘贴防误提交
- 音频 beep 反馈：低音=开始，高音=成功，低沉=无语音
- 支持中英文及多语言（默认 Chinese）
- CUDA 自动加速，无 GPU 时 fallback 到 CPU
- 录音通过 PulseAudio 直接采集，自动选取真实麦克风源

## 环境要求

- Ubuntu，PulseAudio / PipeWire
- conda env `s2t`（Python 3.11）
- X11（xprop、xclip 用于智能粘贴）

## 安装

```bash
conda create -n s2t python=3.11
conda activate s2t
pip install -r requirements.txt
conda install -c conda-forge xclip
```


## 启动

```bash
conda activate s2t
cd /path/to/asrapp

python -m s2t                  # 持续模式
python -m s2t --manual         # 手动开始/停止模式
python -m s2t --debug          # 输出日志文件 + 保存录音 WAV
python -m s2t --manual --debug # 组合使用
```

环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `S2T_LANGUAGE` | `Chinese` | 识别语言，设为空则自动检测 |
| `QWEN3_ASR_MODEL` | `Qwen/Qwen3-ASR-1.7B` | 模型路径或 HF ID |
| `PULSE_SERVER` | 系统默认 | PulseAudio socket 路径 |

## 热键

| 操作 | 效果 |
|------|------|
| 双击 Ctrl | 持续模式：开启监听 / 转写上一段；手动模式：开始 / 停止转写 |
| 长按 Ctrl 2 秒 | 退出 |

## 测试

```bash
export HF_TOKEN=你的token
conda activate s2t
python tests/test_pipeline.py
```

英文 WER 11.9%（LibriSpeech），中文 CER 14.8%（FLEURS cmn_hans_cn），均 PASS。

## 调试

`--debug` 模式下输出：
- 日志：`tmp/s2t.log`
- 录音 WAV：`tmp/recordings/`
