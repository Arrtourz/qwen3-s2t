# 工作协议

我们优先选择稳定、易实现、可验证的方案。

- 每完成一个阶段性步骤后更新此文件
- 已完成事项及时勾选
- 新工作出现时及时替换或追加待办
- 当前阶段默认以此文件作为项目纪要

# 仓库结构

- `mac/`：macOS 菜单栏会议转写应用（双流采集 + 声纹过滤），当前优化重点
- `windows/`：Windows 11 托盘语音输入应用
- `linux/`：保留的 Linux 版本，继续维护配置入口与模型/设备选择
- `third_party/qwen-asr/`：已克隆并已在本机编译通过的 `antirez/qwen-asr`
- `third_party/qwen3-asr.cpp/`：已克隆的对照实现

# mac 版当前状态（2026-10-06 收尾）

内存优化与修复已完成，在 `main` 的 `0952741`。数字都是 phys_footprint（Activity Monitor 口径）：

| 场景 | 优化前 | 优化后 |
|---|---|---|
| 会议进行中 | 6.2 → 7.6 GB，持续上涨 | 2.6–4.6 GB，有上限（1000 段验证） |
| 会议结束 | 7.5 GB | 2.4 GB |
| 空闲 10 分钟后 | 7.7 GB 不降 | **0.33–0.5 GB**（自动卸载模型） |

已移除声纹比对（用户决定）。会议中约 4 GB 是模型权重加上推理时的工作内存；调低缓存释放阈值
（512 / 128 / 0 MB）实测**毫无差别**，因此不再优化。详细过程见下方各轮记录。

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

# mac 长跑内存（2026-10-06，重要）

## 测量口径的坑：RSS 不计 MPS 显存

`ps`/`ru_maxrss` 的 RSS **完全看不到 Metal/MPS 分配**。实测跑了 3 小时的 `s2t.app`：

- `ps` RSS：**246 MB**
- `footprint -p <pid>` 的 `phys_footprint`：**7701 MB**（Activity Monitor 口径），峰值 8672 MB
- 构成：`IOAccelerator (graphics) 5410 MB`（342 个 region）+ MALLOC_NANO 794 MB + MALLOC_SMALL 784 MB

**测内存必须用 `footprint -p <pid>`，别信 RSS。** 启动期优化那段用的是 RSS，
对比仍然有效（同口径），但绝对值远低于真实占用。

## 根因：MPS 缓存分配器按 shape 累积

PyTorch 的 GPU 分配器不把 free 掉的 buffer 还给系统，而是按 shape 缓存。
语音片段长度各不相同（0.5–20 s），**每个新时长就是一个新 shape**，一场长会议下来
缓存远超实际在用的量。实测 40 轮（ASR + WavLM）：

- `current_allocated`（真正在用）**恒定 1975 MB** —— 没有张量泄漏
- `driver_allocated`（含缓存）涨到 **4344 MB**，即 2.4 GB 纯浪费
- `torch.mps.empty_cache()` 后 footprint **5402 → 2579 MB，回收 2.8 GB**

另外 MALLOC 那 1.5 GB 很可能就是下面 segmenter 的静音泄漏（已修）。

## 修法：空闲时归还缓存

`ASRBackend.release_cached_memory(min_slack_bytes)`，设备感知
（MPS 用 `driver_allocated_memory`/`current_allocated_memory`，
CUDA 用 `memory_reserved`/`memory_allocated`，**API 名字不一样，别混**），
slack 超过 `CACHE_SLACK_RELEASE_BYTES = 512 MB` 才动手。两个调用点：

- `_worker_loop` 的 `finally`：**队列排空时**才释放，重建代价落在没人等的片段上
- `end_meeting`：`min_slack_bytes=0` 全量归还，因为 app 会常驻到下一场会议

代价实测：`empty_cache()` 自身 15–35 ms，下一次转写 +41 ms（123 → 164 ms）。
本 app 转写远快于实时，且 segmenter 注释里明确写了 "latency is not a concern"，这个换算值得。

效果（60 轮 ASR + WavLM，`footprint`）：

| | 峰值 | 会后空闲 |
|---|---|---|
| 不释放 | 5731 MB | 5731 MB |
| 释放 | **3662 MB** | **2505 MB** |

峰值 −36%，空闲 −56%。

## 泄漏排查结论（400 轮静默点采样，已定论：无泄漏）

采样方法很重要：每次采样前跑**同一个固定长度的探针片段** + `release_cached_memory(0)` + `gc.collect()`，
这样每次都在同一状态下读数，排除随机片长带来的 ±1 GB 抖动。

| 轮次 | `phys_footprint` | `mps_current_allocated` | `len(gc.get_objects())` |
|---|---|---|---|
| 0 | 3675.9 MB | 1975.1 MB | 347021 |
| 50 | 3717.8 MB | 1975.1 MB | 346836 |
| 100 | 2744.1 MB | 1975.1 MB | 346836 |
| 150 | 3764.2 MB | 1975.1 MB | 346836 |
| 200 | 3770.2 MB | 1975.1 MB | 346836 |
| 250 | 3793.3 MB | 1975.1 MB | 346836 |
| 300 | 3842.8 MB | 1975.1 MB | 346836 |
| 350 | 3835.0 MB | 1975.1 MB | 346836 |
| **400** | **2766.4 MB** | **1975.1 MB** | **346836** |

- `mps_current_allocated` **9 次采样精确恒定 1975.1 MB** → 无张量泄漏
- `len(gc.get_objects())` **8 次采样精确恒定 346836** → 无 Python 对象泄漏
- `phys_footprint` 在 **2744–3843 MB 之间有界振荡**：300 轮涨到 3842.8，400 轮掉回 2766.4
  （和 100 轮的 2744.1 基本同值）。**不是单调爬升**，是内核异步回收 IOAccelerator 页的时机差异。

**教训：别拿单调的几个点就判泄漏。** 我在 250 轮时看到 +117 MB 以为有 0.5 MB/轮 的漂移，
继续跑到 400 轮就掉回去了。判泄漏要看 `mps_current_allocated` 和 `objects`，不是 footprint。

## 内存监控开关（`memory_debug.py`）

默认关。两种开法，任一即可：

```toml
[debug]
memory_monitor = true
memory_monitor_interval_seconds = 60.0
```

```bash
S2T_MEMORY_DEBUG=1 python -m s2t
```

还有托盘菜单 **Memory Report** 可以随时打一次快照（不开监控也能用）。

日志行长这样，四个字段各有分工：

```
MEM footprint=3780MB  mps_in_use=1975MB  mps_cache=72MB  queue=0  buffered=0.4s  objects=346836  gc=365/9/9  (since start +117MB, peak 3793MB)
```

- `mps_in_use` 涨 → **真的张量泄漏**（这是唯一能确诊泄漏的字段）
- `mps_cache` 涨 → 只是分配器缓存，`release_cached_memory()` 会还
- `buffered` 涨 → segmenter 又在囤音频（当初就是这个字段暴露了静音泄漏）
- `queue` 涨 → 转写跟不上，会触发丢最旧
- `objects` 涨 → Python 侧对象泄漏

**取数用 `task_info()` 的 `phys_footprint`（ctypes 直调 Mach API），不是 RSS，也不是 shell 调 `footprint(1)`**
（后者每次约 50 ms）。已和 `footprint(1)` 对账一致。

# mac 启动内存优化记录（2026-10-06）

实测环境：`M 系列 Mac + MPS`，`mac/.venv`，默认 `Qwen3-ASR-0.6B`。
**注意：下表是 RSS 口径**（不含 MPS 显存，见上一节），用于同口径对比启动期开销。

| | 峰值 RSS | 稳态 RSS | 加载 | 预热后单次转写 |
|---|---|---|---|---|
| 优化前 | 2817 MB | 949 MB | 6.0 s | 0.16 s |
| 优化后 | **649 MB** | **649 MB** | 4.9 s | 0.12 s |

峰值 −77%，稳态 −32%，转写延迟无回退。四项改动：

- `backend.py` dtype 修正：checkpoint 存的是 **BF16**，原代码对 MPS 请求 FP16，
  触发全模型转换，加载瞬间两份权重并存 → 单项省 **约 1.9 GB 峰值**。
  `_resolve_dtype()` 统一决策；MPS bf16 内核需 macOS 14+，更老系统回退 FP16。
- `lazy_imports.py` 惰性代理：`import qwen_asr` 会连带 `nagisa`（只给对齐器做日语分词）
  和 `librosa` / `soundfile`（只处理文件路径与非 16k 重采样）——本 app 一个都走不到，
  却要 **+443 MB / 2.6 s**。换成首次属性访问才真导入的代理 → 省 **约 290 MB**。
  代理的 `__spec__` 必须是真的，`transformers` 会 `find_spec()` 探测可选依赖，拿 `None` 直接 `ValueError`。
- `disable_unused_transformers_integrations()`：transformers 在 import 期算好可选依赖开关，
  然后在跟模型一起加载的模块里无条件 import。清掉两个本 app 用不到的开关 → 省 **约 110 MB**：
  - `_sklearn_available`：`generation/candidate_generator.py` 取 `sklearn.metrics.roc_curve`，
    只用于 assisted/speculative decoding 的阈值启发式，需要 draft model，本 app 不传（连带 pandas）
  - `_scipy_available`：`loss/loss_for_object_detection.py` 取 `scipy.optimize` 做 DETR 匈牙利匹配；
    transformers 里 scipy 的消费方全是 vision / 蛋白质折叠 / pop2piano，**没有一个是音频**
  - 两者 transformers 自己都用 `is_*_available()` 守着，清开关等于走它本来就支持的"未安装"分支
- `segmenter.py` 静音泄漏修复，见下。

## segmenter 静音泄漏（真 bug，已修 + 回归测试）

原实现每个 block 都入 `_buffer`，但两个出队条件都要求 `_has_speech`，
**纯静音时缓冲区无上限增长**。系统 tap 没有声音播放时输出数字静音，必然触发。

- 5 分钟纯静音：缓冲 19.20 MB → 修复后 **0.02 MB**（按流算，2 小时安静会议约 460 MB/流）
- 连带效应：2 分钟静音后来 0.5 s 说话，会吐出一个 **120.1 s** 的 segment 丢给 ASR
  （`MAX_ASR_INPUT_SECONDS=1200` 所以不报错，就是白跑 120 秒 encoder 还几乎必然幻觉）
  → 修复后是正确的 **1.6 s**

修法：未攒到语音时只保留 `preroll_ms=300` 的 pre-roll（保住起音），其余丢弃。

## 顺手修的

- `_queue` 原来无 `maxsize`，转写跟不上会无上限堆积；改为 `MAX_PENDING_SEGMENTS=32` + 丢最旧
- `VoiceProfile` 路径原本写死 `default_config_path()`，忽略自定义 `config_path`，
  `S2T_CONFIG_PATH` 一用声纹就存错地方
- 删掉 `controller.py` 里未使用的 `has_voice` 导入

## 实测否掉的方案（别再试）

- ~~**WavLM 转 fp16 / 挪 CPU**：都更差。~~ **此结论错误（RSS 口径看不到 MPS 显存），见下方「声纹比对已移除」。** 原文：checkpoint 是 fp32，转 fp16 要多一份拷贝。
  fp32/MPS **+151 MB** < fp16/MPS +585 MB < fp32/CPU +595 MB。保持现状。
- **绕开 `qwen_asr` 包根直接 import 子模块**：没用，父包 `__init__` 照样执行。
- **推迟加载 WavLM**：`SpeakerVerifier.__init__` 本来就不载模型（`_ensure_loaded` 才载），
  已经是惰性的，无需改。
- **WavLM 加 `use_safetensors=True`**：内存**完全一样**（142 vs 143 MB），但加载稳定慢
  约 0.9 s（1.9 s vs 1.0 s，复测两轮一致）。唯一好处是新装机器少下 395 MB 的 `.bin`，
  一次性磁盘收益换每次启动的延迟，不值得。

## 剩余内存构成（已到地板）

实测分解，总计约 658 MB：

| 组成 | 占用 |
|---|---|
| `torch` | 162 MB |
| ASR 权重（bf16/MPS） | 195 MB |
| 首次转写（MPS 内核/图缓存，一次性） | 112 MB |
| `transformers` | 62 MB |
| `qwen_asr`（已从 443 MB 压到 50 MB） | 50 MB |
| `rumps` + `sounddevice` + `numpy` | 36 MB |
| ~~WavLM 权重 + embed~~ | ~~28 MB~~（RSS 口径，严重低估；声纹已移除） |

torch + transformers 的 224 MB 是框架地板，不碰 PyTorch 没法再降。
真要大降只剩一条路：改用 `qwen_asr_cli` 轻量 C 后端彻底不要 torch，
但 mac 上 `third_party/` 还没建，且声纹过滤（WavLM）仍需 torch——是独立项目不是微调。

## 已知剩余（非内存）

- WavLM 在 HF cache 里下了两份（`.safetensors` + `pytorch_model.bin`，共 772 MB）。
  现在走的是 `.bin`；删掉 `.bin` 会自动回落到 safetensors，但那是用户的 cache，未动。
- `mac/.venv` 1.5 G，其中 gradio / pandas / numba / llvmlite 是 `qwen-asr` 的传递依赖
  且永不导入（gradio 只在 `cli/demo.py`）——只占磁盘不占内存

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
- [ ] mac：用一场真实会议确认内存曲线（开 `[debug] memory_monitor = true` 或用菜单 Memory Report）

## 本轮修复（2026-10-06，续）

- `system_tap.py` **注释与代码矛盾**：注释称"崩溃残留的设备下次启动能找到并销毁"，
  但代码里**根本没有清理逻辑**，destroy 只在正常 stop 路径。
  实测定性：子进程建 tap → `kill -9` → 设备消失。**`"private": 1` 的聚合设备是进程作用域，
  内核会自动回收，不需要清理**。注释已改成记录这个实测结论（原注释描述的是改用唯一 UID 之前的设计）。
- `--manual` / `--continuous` 是**静默空操作**：`recording.mode` 只被写入、
  全代码库没有任何地方读它（mac 版只有 start/end meeting）。已从 mac CLI 和 controller 删掉这条链路。
- `README.md` 的 **Hotkey 和 Tray Menu 两节描述的是 Windows 版行为**：
  snapshot、Stop、"Settings 打开设置窗口"都不存在。已按实际菜单重写，并补了 Debugging Memory 一节。
- `release_cached_memory` 的"释放 0 字节"是**正常现象不是故障**：刚加载完模型 MPS 就有
  约 330 MB 的 slack 属于内部碎片，`empty_cache()` 释放不了；只有变长片段堆出来的缓存才可回收
  （实测：跑 3 次转写后 slack 447 MB，释放 92.4 MB，reserved 2017.2→1924.9 吻合）。
  freed=0 时降到 debug 级日志，避免误导。

## 已确认的死代码（未删，等确认）

- `s2t/platform/macos/settings.py`（274 行）**零引用**，连测试都没引用。
  `controller.open_settings()` 的注释写明 Tkinter 在 rumps 的 NSApplication 下会崩，
  已改成用编辑器打开 config.toml。这 274 行是被放弃的实现。
- `s2t/platform/macos/paste.py`（38 行）零引用（只有 `tests/test_paste.py` 测它）。
  会议转写器写 Markdown 文件，不需要粘贴。
- 死配置字段：`PasteConfig` 整个、`RecordingConfig.input_device`、
  `RecordingConfig.continuous_window_seconds`、`RecordingConfig.mode`。
  （同 dataclass 里的 `sample_rate` / `block_duration_ms` 是活的，别一起删。）

## 启动链路冒烟验证

`_resolve_config` → `_build_ui`（构造 MacTrayApp，能抓到签名漂移）→ `_load_heavy`
→ `log_memory_report` → `_on_segment` → `release_cached_memory` → `shutdown` 全通，
托盘菜单 11 项与预期一致。改了 tray 签名/config/CLI 之后一定要跑这个，单测覆盖不到（需要 AppKit）。

## 本轮修复（2026-10-06，第三轮）

### 单实例锁 race（真 bug，已修）

`SingleInstanceLock.release()` 原来会 `unlink` 锁文件。flock 的锁在**打开的 fd** 上，
不在文件的存在性上，所以删掉文件之后下一个进程会创建**新 inode** 并成功加锁 ——
旧持有者还在跑，于是**两个实例同时运行**。已用三进程脚本实证复现。

触发窗口在 `close()` 和 `unlink()` 之间，**"退出后立刻重启"正好撞上**。

修法：**永不删锁文件**。进程死亡（含 SIGKILL）内核会自动释放 flock，残留一个零长度文件无害。
顺带两处加固：

- `os.open(O_RDWR|O_CREAT)` 不带 `O_TRUNC` —— 原来用 `open(path,"w")`，
  抢锁失败的进程会把持有者记录的内容截断掉
- 拿到锁之后把 pid 写进文件，`cat ~/.config/s2t/s2t.lock` 能直接回答"谁占着"

测试 7 个，含**子进程 SIGKILL 后锁自动释放**的验证（证明确实不需要清理残留文件）。

### 提示音回灌 tap —— 查了，不是 bug

`beep()` 从默认输出播音，而 system tap 捕获**所有**系统输出，所以自己的提示音会进
"Them" 流。实测三个音都确实生成了 segment，但 **VAD 全部挡住**：

| 音 | 频率/时长 | voiced 比例 | 过 VAD |
|---|---|---|---|
| start | 620 Hz 0.12 s | 9% | 否 |
| done | 880 Hz 0.16 s | 12% | 否 |
| error | 280 Hz 0.18 s | 14% | 否 |

原因是提示音只占 1.30 s 片段里的 120–180 ms，voiced 帧比例远低于门槛 ——
正好验证了 `voice.py` 坚持用"帧比例"而不是整段均值的设计。

**但余量很薄**：当前 config 的 `voice_min_voiced_ratio` 是 0.20，而 error 音是 0.14，
只差 6 个百分点。**谁要调低这个阈值，先跑一遍 `/tmp/test_beep_feedback.py` 那套检查**，
否则提示音会开始被转写进会议记录。

## 本轮修复（2026-10-06，第四轮）

- **会议记录被覆盖（数据丢失，已修）**：文件名只精确到秒，`open_session()` 用 `write_text()`
  写表头。同一秒内 End → Start（双击热键就够）会复用文件名，**把刚结束的会议记录整个清空**。
  已实测复现。改用 `open("x")` 独占创建，重名时依次取 `_2`、`_3`… 后缀。
- **热键回调在后台线程改 AppKit UI**：pynput 监听器是独立 `threading.Thread`，
  回调直接走 `toggle_meeting` → `tray.set_recording()` 改状态栏标题，违反主线程约束。
  改为热键只 set 一个 `Event`，由已有的 0.25 s 主线程定时器（`_main_thread_tick`）执行切换。
- **热键默认值三处互相矛盾**：`DEFAULT_HOTKEY="ctrl+alt+h"`，但生成的 config 模板写
  `hotkey = "none"`，代码注释说"默认关"。config 里省略 hotkey 行就会**静默打开** pynput 的
  CG event tap。已统一为默认关。
- 我上一轮写的 README 说"Default `ctrl+alt+h`"是错的，已更正为默认关 + 开启方法。


# 长时间后台挂载的内存（2026-10-06，第五轮，重点）

## 用户问"7 GB 正常吗"——不正常

旧进程（PID 90875，修复前代码）15:23 会议结束后空闲 3 小时以上，footprint 仍是 **7700 MB**，
两小时内没有任何变化。`heap -s` 看堆，发现 **2116 个 `MPSGraphExecutable`** 和 1468 万个
MLIR/MPSGraph 内部节点，合计 **1.58 GB**。这是 Metal 后端**按每种输入长度编译一张图并永久缓存**，
`empty_cache()` 释放不了。

## 声纹比对已移除（用户决定）

用 phys_footprint 重测才发现 WavLM 是最大单项，之前用 RSS 测出的"151 MB"是**错的**：

| WavLM 跑在 | 加载 | 300 段后 |
|---|---|---|
| MPS（原代码） | **+1503 MB** | **+3246 MB** |
| CPU | +257 MB | +1624 MB（20 s 片段峰值约 1.8 GB 被常驻保留，不是持续泄漏） |

用户日志里共有 3957 次声纹比对。试过的替代方案：截到 10 s 能省约 1 GB，但会拉低长片段的相似度，
本人发言会被多丢（>10 s 片段占 17%，中位相似度 0.73–0.76）；补零配合 attention mask 会让相似度跳变
0.437→0.613，正好跨过阈值。用户最终决定直接去掉。

删除内容：`speaker_id.py`、`test_speaker_id.py`、Enroll My Voice 菜单、`speaker_filter`/`speaker_threshold`。
旧 config.toml 里的这两个键会被**静默忽略**（解析器用 `.get()`），有测试覆盖。
`~/.config/s2t/voice_profile.json` 是用户数据，**没有删**。

效果：会后空闲 3732 → **2456 MB**，会议中峰值约 3.7 GB。

## ASR 输入补零对齐到 1 s（`SHAPE_BUCKET_SAMPLES`）

把图的数量限制在约 20 张。400 段测试中图缓存增长 +99 → **+22 MB**。
10 段真实录音补零前后**转写逐字一致**。只用于 GPU 设备。

## 空闲卸载模型（`[memory] idle_unload_minutes`，默认 10，0 = 不卸载）

会议之间模型常驻约 2.4 GB。空闲超时后卸载，下次 Start Meeting 在后台重载（实测 3.8–4.4 s）。
录音**立即开始**，前几秒的片段在队列里等模型加载好，不会丢。backend 内部用一把 `RLock`
串行化 load / transcribe / unload / 释放缓存。

端到端实测（真模型、真录音、临时配置目录）：

| 阶段 | footprint |
|---|---|
| 会议结束 | 2565 MB |
| **空闲超时后** | **438 MB** |
| 再开会自动重载 | 2549 MB |

## 顺手修的：每场会议最后一句话会丢（数据丢失）

`end_meeting` 先 `recorder.stop()` 把最后的片段刷进队列，然后**立刻**关闭记录文件。
worker 转写完再 `append()` 时文件已关，直接丢弃。用户日志里有实证，
例如一段完整的中文长句和多段 `[🔊 Them]` 的结尾发言，都只出现在日志里、没进会议记录。
现在改为后台线程 `queue.join()` 等队列转写完再关文件。注意 `_enqueue` 淘汰旧片段时也要
`task_done()`，否则 `join()` 会永远挂住（有测试覆盖）。

## 测试注意

冒烟脚本**别用真实配置目录**：前几次跑的时候往用户的 `~/.config/s2t/logs/s2t.log` 里写进了
"Shutting down" 等行，差点被误判成 app 退出时挂住。要设 `S2T_CONFIG_PATH` 指向临时目录。


## 收尾（2026-10-06）

- 新旧版本对照（同一场模拟会议，400 段真实录音，旧版开声纹）：旧版 6174→7648 MB 线性上涨、
  会后 7504 MB；新版 4185–4561 MB、会后 2391 MB、卸载后 491 MB。新版跑 1000 段仍有上限，
  `mps_in_use` 稳定在 1572–1607 MB。
- 真实 app 重启后：启动 2157 MB，空闲 10 分钟后 19:22:22 自动卸载，降到 **333 MB**。
- 缓存释放阈值 512 / 128 / 0 MB：平均都是 4092 MB、耗时 250–254 ms，没有区别。我之前说
  "更频繁释放还能再压"是错的，不做。
- 直接提交在 `main`；`mac-long-run-memory` 分支指向同一个 commit，保留未删；未 push。
- **静默启动**（用户要求）：去掉 Start Meeting 的提示音和 app 启动时的 "Ready" 通知，
  也去掉开会时的 Voice Isolation 提示；状态以菜单栏图标为准（⏳ → 🎙 → 🔴）。
  保留：启动失败 / 音频设备错误的通知。
- **完全无声**（用户要求）：End Meeting 的提示音也去掉了，`sound.py` 已删除，app 不再播放任何声音。
  测试直接拦截 `sounddevice.play`，以后不管谁再加提示音都会被发现。

## 配置收尾（2026-10-06，用户授权"你来决定"）

- **`language` 加了真正的 `"auto"`**：原来空字符串会被静默当成 `"Chinese"`，根本没法自动识别。
  实测固定为 `"English"` 时，短中文会被翻成英文（`'在这里。'` 变成 `'In here.'`），噪声会被幻觉成 `'The.'`；
  长句两种设置结果一样。新默认值和用户配置都改成了 `"auto"`。
- 删掉不生效的 `meeting.silence_rms`（只有非自适应模式才读，而这个模式从来没开过）和
  `recording.channels`（从没被读取）。顺带改正 segmenter 里写错的注释。
- **外放回声去重 `meeting.drop_mic_echo`（默认开）**：用笔记本扬声器时，麦克风会把对方的话再录一遍。
  规则：`Me` 行与最近 10 秒内某条 `Them`（或相邻两条拼起来）的相似度 ≥ 0.8 就丢弃，少于 6 个字的不判。
  第一版把最近的 `Them` 全部拼成一串来匹配，回放历史日志时会误删 **17.7%** 的 `Me` 行，已废弃。
  现在的版本在历史日志里命中 12.4%，抽样看基本都是真回声：同一句话间隔 0–2 s，相似度中位 0.95。
  换句话说，**旧的声纹过滤一直没挡住这些回声**。
- 用户的 `~/.config/s2t/config.toml` 已按新格式重新生成，值都保留（包括 `voice_min_voiced_ratio = 0.2`），
  原文件备份为 `config.toml.bak-2026-10-06`。
- **用户改主意（同日）**：语言设为 `"English"`（代码里仍保留 `"auto"` 选项，新生成的配置默认是 `"auto"`）；
  **外放回声去重整个撤掉**（`echo.py` 和 `drop_mic_echo` 已删除）。用外放时，对方的话仍会在 `Me` 里重复出现，
  戴耳机就没有这个问题。用户配置已按新格式重新生成。

# Zoom 入会失败（2026-10-09，严重 bug，已修）

**现象**：先在 s2t 点 Start Meeting，再进 Zoom，Zoom 进不去会议。

**根因**：系统音频 tap 的聚合设备设置了 `tapautostart: 1`。只要 tap 存在，**其他 app 新启动音频 IO
时都会在 coreaudiod 里卡约 35 秒**：系统日志是 `HALS_IOContext_Legacy_Impl::StartIOThread … Error: 0x3C`
（ETIMEDOUT）。那天早上 09:00:19 s2t 先开录，Zoom 连续 3 次音频启动超时后退出，重开之后又卡死，
直到 09:30 关掉 s2t 才恢复。Zoom 先入会、后开 s2t 时不会出现，因为 Zoom 的音频在 tap 出现之前就已经启动了。
**这个 bug 早就有**，旧版本的 tap 代码（c78bf0f）复现出同样的 34.86 s，并不是这次改动引入的。

**复现与定位**（另起一个进程打开麦克风，模拟 Zoom）：

| s2t 状态 | 打开麦克风耗时 |
|---|---|
| 什么都没开 | 0.13 s |
| 只开麦克风流 | 0.09 s |
| 只开 tap | 36.22 s |
| tap + 麦克风 | 34.83 s |

| 聚合设备配置 | 耗时 |
|---|---|
| 现状 | 38.72 s |
| 加主设备 / 子设备（输出设备） | 38.26 s |
| 打开漂移补偿 | 38.61 s |
| **`tapautostart: 0`** | **0.12 s** |

排除掉的方向：16 kHz 采样率（`system_profiler` 显示内置麦克风一直是 48000 Hz，PortAudio 是软件重采样）、
聚合设备缺少时钟主设备。

**修复**：`tapautostart: 0`。tap 会随聚合设备自己的输入流一起启动，系统音频照常能录到。
在 app 里实测：会议进行中另一个进程打开麦克风耗时 0.09 s，`🔊 Them` 中英文都正常转写。
`tests/test_system_tap_config.py` 固定了这个值。

**排查踩过的坑**：zsh 里 `log` 是内置命令，查系统日志要写 `/usr/bin/log show`。
在这个 shell 里没有麦克风 / 系统录音权限，只能测"启动耗时"，没法测"录到了什么"，后者要在 app 里验证。

# 外放回声消除（2026-10-09，已上线）

用户有时开着笔记本扬声器开会，麦克风会把对方的话再录一遍。约束：**不能明显增加内存**。

**选型**：WebRTC AEC3（`livekit` 的 `AudioProcessingModule`），以系统音频 tap 作为参考信号。

| 方案 | 额外内存 | 真实外放 A/B（2 次，各 5 条回声） |
|---|---|---|
| 不做回声消除 | — | 5/5、5/5 留在 `Me` |
| **WebRTC AEC3（livekit）** | **+16–18 MB** | **1/5、1/5** |
| Speex（pyaec） | +2–4 MB | 5/5、5/5（合成测试 27.7 dB，真实房间混响下基本没用） |
| 苹果 VoiceProcessingIO | — | 没试：要重写麦克风采集，和 Zoom 冲突的问题同在 CoreAudio 这一层 |

最终在 app 里实时测试：麦克风原始音量 0.083（回声和前两次一样强），`Them` 5 行，**`Me` 0 行**，会议中 footprint 2191 MB（不做回声消除时是 2264–2373 MB）。

**已知弱点**：两人同时说话时，AEC3 会压低用户自己的声音（合成测试）。用户说话时对方一般不说，影响不大。
用户单独说话时声音不受影响（合成测试转写一字不差）。

**实现**：`s2t/core/aec.py`：负责 10 ms 分帧和跨块余数，两个音频线程共用一把锁，出任何错就退回原样输出。
配置项 `meeting.echo_cancellation`（默认 true）；只在 `system_source` 是 tap 或 device 时启用。
livekit 延迟导入，导入失败时照常录音、不做回声消除。

**测试经验**：
- 合成测试的"人声"音量和真实麦克风对不上（连没处理的音频都卡在 VAD 阈值上），判断不了人声损伤，要用真实录音
- 波形相关度不适合当指标（相位和延迟敏感），要用"转写结果"判断
- 测试素材要用有人说话的视频，纯音乐只会输出 "Music."，被当填充词过滤掉
- 调试开关 `S2T_RECORD_RAW=1`（用 `open --env S2T_RECORD_RAW=1 dist/s2t.app` 启动）：把原始麦克风和系统音频写成 wav，
  存到 `~/.config/s2t/raw-audio/`。**平时别开**，否则每场会议都会存原始音频。
