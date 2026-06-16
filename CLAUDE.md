# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 开发板 SSH 登录

开发板为泰山派（LCKFB），代码部署在 `/userdata/code/GC2026/`。

```bash
ssh -o StrictHostKeyChecking=no -i "C:/Users/IVEN/.ssh/tspi" lckfb@169.254.133.100
```

SSH config (`~/.ssh/config`):
```
Host 泰山派-wire
  HostName 169.254.133.100
  User lckfb
  IdentityFile "C:\\Users\\IVEN\\.ssh\\tspi"
```

### 代码同步流程

开发板上的 `/userdata/code/GC2026` 是 git 仓库。修改代码后：

1. **本地**：`git push` 推送到远程
2. **开发板**：`git pull` 拉取最新代码

开发板上使用 `uv` 运行：

```bash
ssh lckfb@169.254.133.100
cd /userdata/code/GC2026
uv run main
```

## 常用命令

本项目使用 `uv` 作为包管理器。所有运行均通过 `uv run` 调用 `pyproject.toml` 中定义的入口。

| 命令 | 说明 |
|------|------|
| `uv sync` | 安装依赖（根据 `uv.lock`） |
| `uv sync --extra test` | 安装包含测试依赖 |
| `uv run app` | 启动桌面调参应用（PyQt6） |
| `uv run main` | 启动嵌入式主程序（三个协程并行） |
| `uv run setup color --capid 0` | 颜色阈值调试工具 |
| `uv run setup colorring --capid 0` | 色环检测阈值调试工具 |
| `uv run img_trans` | 图像传输（Linux 发送 / Windows 接收） |

## 项目架构

### 协程模型

`main.py` 通过 `asyncio.gather` 并行运行三个协程：

1. **`main()`** — 图像处理主循环：从串口读取 `@...#` 格式任务指令（`R`/`G`/`B`/`C`），调用检测器处理，结果通过串口回写，处理后的图像写入 `img_need_to_send`。
2. **`board_show()`** — OLED 状态显示：读取拨码开关切换 `RUN_MODE`（`main`/`debug`），在 OLED 上显示当前模式、服务端 IP 及识别结果。
3. **`img_trans()`** — UDP 图传：将 `img_need_to_send` 通过 UDP 发送到客户端。`debug` 模式直接发送原始图像。

### 模块关系

```
main.py
├── applications.py          # 应用逻辑层，调度检测器
│   └── detector/
│       ├── ColorDetect.py   # TraditionalColorDetector（物料颜色检测）
│       ├── ColorRingDetect.py # ColorRingDetector（圆环检测）
│       └── Detect.py        # 检测器基类（提供锐化方法）
├── utils/
│   ├── UART.py              # 串口通信（Uart 继承 serial.Serial）
│   ├── gpio.py              # GPIO 抽象（LED / Switch / OLED_I2C）
│   ├── _cap.py              # 摄像头封装（Cap / InterpolatedCap）
│   └── ConfigLoader.py      # YAML 配置加载
└── ImgTrans/
    ├── IImgTrans.py         # 发送/接收接口基类
    └── ImgTrans.py          # TCP / UDP 图传实现
```

### 平台差异

- **Linux（开发板）**：使用 `utils.Cap()` 初始化摄像头（基于 v4l2），支持 GPIO/OLED/串口硬件操作。通过 `periphery.GPIO` 操作泰山派 GPIO，引脚格式为 `"GPIO1-A2"`。
- **Windows**：使用 `cv2.VideoCapture(0)`，GPIO 相关功能降级为空操作（`OLED_I2C`、`LED`、`Switch` 均为无操作实现）。

### 配置

颜色检测阈值和圆环检测参数存储在 `config.yaml` 中，可通过 `uv run setup color` / `uv run setup colorring` 交互式调节并保存。

### 事件循环阻塞注意事项

本项目重度依赖 `asyncio`，以下操作会阻塞事件循环，必须在线程中执行：

- **串口读取**（`UART.py`）：`serial.Serial.read()` 是阻塞的，整包读取应在线程中完成，通过 `asyncio.Future` 回调结果。
- **图像编码**（`ImgTrans/ImgTrans.py`）：`cv2.imencode('.jpg', ...)` 是 CPU 密集型操作。
- **GPIO / OLED 操作**（`utils/gpio.py`）：`OLED_I2C.text()` 和 `display()` 涉及 I2C 通信和 PIL 绘制，应通过 `run_in_executor` 执行。
- **摄像头读取**（`utils/_cap.py`）：`Cap.read()` 继承自 `cv2.VideoCapture`，虽已在主循环中同步调用，但在协程环境中仍需注意帧率对齐。

`Uart.new_read()` 和 `Uart.new_write()` 提供异步包装。修改这些函数时，避免在协程中直接调用同步阻塞的 `super().read()` / `super().write()`。
