# 待研究的问题

- 继续收敛更干净的控制台退出路径，区分交互式 `Ctrl+C` 与外部 `CTRL_BREAK_EVENT`
- 在真实 Win11 环境继续验证热键、托盘通知、录音链路的长期稳定性
- 评估是否需要在第二阶段增加安装器、开机自启与系统权限引导

# 已定决策

- 原始 Linux 版本代码与测试归档到 `linux/` 子目录
- 当前 Windows 重构实现整理到 `windows/` 子目录
- 当前阶段不继续开发 Linux 版本，目标平台是 `Windows 11`
- 以当前工作区为重构载体，但架构按“新项目”标准重建
- 技术栈使用 `Python`
- 产品形态改为 `系统托盘常驻应用`
- 第一阶段交付 `源码可运行 MVP`，暂不做 `exe` 或安装器
- 配置入口改为 `config.toml`，不再依赖环境变量作为主入口
- 支持 `S2T_CONFIG_PATH` 作为测试 / 临时配置覆盖入口
- 默认热键恢复为 `双击 Ctrl`
- 默认录音模式恢复为 `continuous`
- 默认模型切换为 `Qwen/Qwen3-ASR-0.6B`
- 配置文件和 CLI 都支持模型选择：`0.6b / 1.7b`
- 配置文件和 CLI 都支持设备选择：`auto / cpu / gpu`
- 托盘菜单新增 `Settings`，提供图形化设置窗口
- ASR 后端保留抽象层，当前仅实现 `Qwen3-ASR`
- 运行环境使用 CUDA 版 `torch`，在 `auto` 模式下优先走 GPU

# Features

- 托盘驻留与最小菜单
- 全局热键触发
- 默认 `double_ctrl` 触发
- 默认 `double_ctrl` 模式下支持长按 `Ctrl` 约 2 秒退出
- `continuous` 与 `manual` 两种录音模式
- Qwen3-ASR 转写
- 支持 `0.6b / 1.7b` 模型选择
- 支持 `auto / cpu / gpu` 设备选择
- 支持图形化设置热键、模式、模型和设备
- 自动粘贴到当前活动应用
- 终端窗口与普通 GUI 窗口使用不同粘贴策略
- 配置热重载
- 日志目录快速打开
- 基础提示音 / 通知反馈
- Windows BOM 配置兼容
- single-instance lock，避免重复启动与热键冲突

# 当前状态

- `python -m s2t` 已在 Win11 + RTX 3080 环境跑通
- 模型已确认能从 `cpu` 切到 `cuda:0`
- 默认热键已恢复为双击 `Ctrl`
- 默认配置已恢复为 `continuous`
- 默认模型已切为 `Qwen/Qwen3-ASR-0.6B`
- `%APPDATA%\\s2t\\config.toml` 已补齐 `variant` 与 `device` 字段
- 设置 UI 保存后会写回 `config.toml` 并立即热重载
- 自动化测试当前通过，最新结果为 `17 passed`

# Benchmark Notes

- 测试环境：Win11 + RTX 3080 + CUDA `torch`
- 测试音频：本地 TTS 英文样本
- 缓存态结果：
  - `Qwen/Qwen3-ASR-0.6B`
    - `load_seconds`: `5.081`
    - `first_transcribe_seconds`: `2.47`
    - `gpu_peak_memory_mb`: `1789.2`
  - `Qwen/Qwen3-ASR-1.7B`
    - `load_seconds`: `6.153`
    - `first_transcribe_seconds`: `2.352`
    - `gpu_peak_memory_mb`: `4489.9`
- 当前结论：默认模型切到 `0.6B` 更合理，延迟接近但显存占用显著更低

# Pipeline/Todolist

- [x] 重建包结构，拆分 `core` 与 `platform/windows`
- [x] 新增 `config.toml` 配置系统与默认配置生成
- [x] 新增 Windows 热键服务
- [x] 新增 Windows 录音服务
- [x] 新增 Windows 粘贴服务
- [x] 新增 Windows 托盘服务
- [x] 接入 Qwen3-ASR 后端抽象
- [x] 切换到 CUDA 版 `torch`
- [x] 恢复 `double_ctrl` 默认热键
- [x] 恢复长按 `Ctrl` 退出
- [x] 恢复 `continuous` 默认模式与 CLI 模式切换
- [x] 修复 Windows BOM 配置解析
- [x] 增加 single-instance lock，避免重复启动与热键冲突
- [x] 增加启动阶段基础错误提示
- [x] 增加 Windows 终端感知粘贴策略
- [x] 增加本地模型对比基准脚本
- [x] 实测 `Qwen3-ASR-0.6B` 与 `Qwen3-ASR-1.7B`
- [x] 根据实测结果决定默认模型
- [x] 增加模型与设备选择能力
- [x] 增加图形化设置窗口
- [ ] 在真实 Win11 环境验证热键注册稳定性
- [ ] 在真实 Win11 环境验证麦克风录音链路
- [ ] 在真实 Win11 环境验证托盘通知与退出行为
- [ ] 收敛更干净的控制台退出体验
- [ ] 补充错误提示与恢复策略
- [ ] 第二阶段再考虑 `exe` 打包与安装流程
