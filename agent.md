# 工作协议

我们优先选择稳定、易实现、可验证的方案。

- 每完成一个阶段性步骤后更新此文件
- 已完成事项及时勾选
- 新工作出现时及时替换或追加待办
- 当前阶段默认以此文件作为项目纪要

# 仓库结构

- `windows/`：当前主线，Windows 11 托盘语音输入应用
- `linux/`：保留的 Linux 版本，继续维护配置入口与模型/设备选择
- `third_party/qwen-asr/`：已克隆并已在本机编译通过的 `antirez/qwen-asr`
- `third_party/qwen3-asr.cpp/`：已克隆的对照实现

# 已定决策

- 当前主开发目标平台是 `Windows 11`
- 技术栈使用 `Python`
- 产品形态是 `系统托盘常驻应用`
- 配置入口统一为 `config.toml`
- Windows 默认热键是 `ctrl+alt+h`
- Windows 默认录音模式是 `continuous`
- Windows 默认模型是 `Qwen/Qwen3-ASR-0.6B`
- Windows 不再支持长按 `Ctrl` 退出
- Windows 退出方式保留为终端 `Ctrl+C` 和托盘 `Exit`
- Linux 版本继续保留，但不是当前主开发目标

# 当前功能

## Windows

- 托盘驻留与托盘菜单
- 全局热键触发
- `continuous` / `manual` 两种录音模式
- 自动转写与自动粘贴
- 终端感知粘贴策略
- 设置窗口，可修改：
  - Backend
  - Hotkey
  - Recording mode
  - Model variant
  - Device
  - Lightweight binary path
  - Lightweight model directory
- 单实例锁
- 配置热重载

## Linux

- 双击 `Ctrl` 触发录音
- `continuous` / `manual` 两种录音模式
- 模型选择：`0.6b / 1.7b`
- 设备选择：`auto / cpu / gpu`
- `config.toml` 配置入口

# 后端策略

当前 Windows 已支持两类后端：

- `qwen3_asr`
  - Python + PyTorch + `qwen_asr`
  - 支持 `auto / cpu / gpu`
  - 仍是默认后端
- `qwen_asr_cli`
  - 面向 `antirez/qwen-asr` 的轻量外部 CLI 后端
  - 当前按子进程调用
  - 仅支持 `cpu / auto`
  - 调用方式：
    - `qwen_asr -d <model_dir> -i <temp.wav> --silent [--language <language>]`

说明：

- `qwen_asr_cli` 通过 `binary_path` 和 `path_or_id` 接入本地可执行文件与模型目录
- 若 `%APPDATA%\\s2t\\tmp` 不可写，轻量后端会回退到当前工作目录下的 `runtime-temp`
- 为了支持 Windows，本地已对 `third_party/qwen-asr` 做了两处兼容修复：
  - `qwen_asr_kernels.c`：CPU 核心数检测改为 Windows 分支
  - `qwen_asr_safetensors.c/.h`：`mmap` 改为 Windows 文件映射

# 当前状态

- Windows 主线已在 `Win11 + RTX 3080` 环境跑通
- 轻量后端接入已经完成代码、配置、CLI 参数、设置 UI、测试
- `MSYS2 UCRT64` 已安装
- `qwen_asr.exe` 已在本机编译成功
- `Qwen3-ASR-0.6B` 模型文件已下载到 `third_party/qwen-asr/qwen3-asr-0.6b`
- 轻量后端独立 CLI 已通过真实 CPU 转写验证
- `python -m s2t --backend lightweight --device cpu --model 0.6b` 已启动成功并进入常驻
- 普通组合键热键不再走 `keyboard.add_hotkey()`，而是走 Win32 原生 `RegisterHotKey`

# Benchmark 记录

- 测试环境：`Win11 + RTX 3080 + CUDA torch`
- 缓存态结果：
  - `Qwen/Qwen3-ASR-0.6B`
    - `load_seconds`: `5.081`
    - `first_transcribe_seconds`: `2.47`
    - `gpu_peak_memory_mb`: `1789.2`
  - `Qwen/Qwen3-ASR-1.7B`
    - `load_seconds`: `6.153`
    - `first_transcribe_seconds`: `2.352`
    - `gpu_peak_memory_mb`: `4489.9`
- 结论：
  - 默认模型继续保留 `0.6B`
  - 首轮延迟接近
  - 显存占用明显更低

# 已完成

- [x] 仓库拆分为 `windows/` 和 `linux/`
- [x] Windows 配置系统 `config.toml` 落地
- [x] Windows 热键、录音、粘贴、托盘、设置窗口
- [x] Windows 单实例锁
- [x] Windows 模型选择：`0.6b / 1.7b`
- [x] Windows 设备选择：`auto / cpu / gpu`
- [x] Windows 默认模型切换为 `0.6B`
- [x] Windows 默认热键切换为 `ctrl+alt+h`
- [x] Windows 移除长按 `Ctrl` 退出
- [x] Windows 控制台 `Ctrl+C` 退出链路补强
- [x] Linux 补齐模型/设备配置入口
- [x] 克隆 `antirez/qwen-asr` 和 `predict-woo/qwen3-asr.cpp`
- [x] Windows 接入 `qwen_asr_cli` 轻量后端
- [x] 新增 `--backend python|lightweight`
- [x] 设置窗口支持切换后端
- [x] 配置文件支持：
  - `model.provider`
  - `model.binary_path`
- [x] 轻量后端单测与集成测试通过
- [x] 在本机安装 `MSYS2 UCRT64`
- [x] 在本机编译 `third_party/qwen-asr/qwen_asr.exe`
- [x] 下载 `third_party/qwen-asr/qwen3-asr-0.6b`
- [x] 真实运行 `qwen_asr.exe -d qwen3-asr-0.6b -i samples/jfk.wav --silent`
- [x] 修复 `--backend lightweight --model 0.6b` override 路径错误
- [x] 普通组合键切换到 Win32 原生热键实现

# 测试记录

- `conda run -n s2t-win pytest windows\\tests\\test_backend.py windows\\tests\\test_config.py windows\\tests\\test_config_save.py windows\\tests\\test_app.py -q -p no:cacheprovider --basetemp ...`
  - `17 passed`
- `conda run -n s2t-win pytest windows\\tests\\test_hotkey.py windows\\tests\\test_controller.py -q -p no:cacheprovider --basetemp ...`
  - `8 passed`
- `conda run -n s2t-win python -m compileall windows\\s2t windows\\tests`
  - 通过

# 待办

- [ ] 对比轻量后端与 Python/CUDA 后端的启动耗时和转写时延
- [ ] 评估是否把轻量后端做成持久化子进程，而不是每次转写新起一次进程
- [ ] 继续做 Win11 热键、录音、托盘稳定性验证
- [ ] 整理并提交 `third_party/qwen-asr` 的 Windows 构建说明
