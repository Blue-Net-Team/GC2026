# GC2026

GC2026 是一个基于 OpenCV 的计算机视觉项目，主要用于物料颜色检测、圆环检测以及图像传输。项目支持在 Linux（嵌入式板卡）和 Windows 环境下运行，可通过串口接收任务指令并返回识别结果。

此外，项目包含一个跨平台桌面调参应用（`app/`），用于通过 UDP 接收图传画面、可视化调节参数、远程部署配置和管理服务。

***

## 功能简介

- **颜色物料检测**：支持红（R）、绿（G）、蓝（B）三种颜色的物料识别与定位
- **圆环检测**：检测图像中的圆环目标
- **图像传输（UDP）**：支持将处理后的图像通过 UDP 实时传输到服务端
- **OLED 状态显示**：在支持的板卡上显示当前运行模式、服务端 IP 及识别结果
- **参数调试工具**：提供交互式颜色阈值调试命令行工具

***

## 环境要求

| 项目     | 要求                                   |
| ------ | ------------------------------------ |
| Python | >= 3.12                              |
| 操作系统   | Linux（推荐，用于嵌入式部署）/ Windows（用于本地开发调试） |
| 包管理器   | [uv](https://docs.astral.sh/uv/)     |

***

## 安装 uv

本项目使用 [uv](https://docs.astral.sh/uv/) 作为 Python 包管理工具。如果你还没有安装 uv，请根据你的操作系统选择以下方式之一：

### Windows

使用 PowerShell 安装：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

或者使用 winget：

```powershell
winget install --id=astral-sh.uv  -e
```

### Linux / macOS

使用 curl 安装：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

或者使用 Homebrew（macOS）：

```bash
brew install uv
```

安装完成后，验证 uv 是否安装成功：

```bash
uv --version
```

***

## 项目环境配置

### 1. 克隆项目

```bash
git clone <你的仓库地址>
cd GC2026
```

### 2. 创建虚拟环境并安装依赖

本项目已配置好 `pyproject.toml` 和 `uv.lock`，使用 uv 一键安装依赖：

```bash
# 仅安装嵌入式主程序所需依赖
uv sync

# 如果要开发/运行桌面调参应用，需要额外安装 app 依赖
uv sync --extra app
```

该命令会自动：

- 读取 `.python-version` 文件，使用 Python 3.12
- 创建项目虚拟环境
- 根据 `uv.lock` 安装所有依赖包

> 其他可选依赖：
>
> ```bash
> uv sync --extra test   # 测试依赖
> uv sync --extra board  # 嵌入式 GPIO 依赖
> ```

### 3. 激活虚拟环境

在运行项目前，需要激活 uv 创建的虚拟环境：

```bash
# Windows (PowerShell)
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate
```

或者使用 uv 直接运行命令（无需手动激活）：

```bash
uv run python app.py
```

***

## 项目结构

```
GC2026/
├── app.py                  # 桌面调参应用入口
├── main.py                 # 嵌入式主程序入口
├── applications.py         # 应用逻辑（颜色/圆环检测）
├── setup.py                # 参数调试工具入口
├── img_trans.py            # 图像传输入口
├── config.yaml             # 颜色检测配置文件
├── pyproject.toml          # 项目配置与依赖
├── uv.lock                 # 依赖锁定文件
├── .python-version         # Python 版本指定（3.12）
├── app/                    # 桌面调参应用包
├── ImgTrans/               # 图像传输模块（UDP 发送/接收）
├── detector/               # 检测器模块（颜色、圆环）
├── utils/                  # 工具模块（串口、GPIO、摄像头等）
└── run_auto/               # 自动运行脚本与服务配置
```

***

## uv run 入口一览

本项目在 `pyproject.toml` 中定义了以下入口，均可通过 `uv run <入口名>` 直接运行。

| 入口名               | 功能          | 有参数 |
| ----------------- | ----------- | --- |
| `app`             | 启动桌面调参应用   | 否   |
| `main`            | 启动嵌入式主程序   | 否   |
| `setup color`     | 交互式调节颜色检测阈值 | 是   |
| `setup colorring` | 交互式调节色环检测阈值 | 是   |
| `img_trans`       | 图像传输（发送/接收） | 否   |

***

### 1. `uv run app` — 桌面调参应用

启动 PyQt6 桌面调参应用，提供 UDP 图传接收、颜色/色环参数调节、配置管理、SSH 服务管理和日志查看等功能。

```bash
# 首次运行前确保已安装 app 依赖：uv sync --extra app
uv run --extra app app
```

### 2. `uv run main` — 嵌入式主程序

无额外参数，启动后并行运行三个异步协程：

| 协程      | 功能                                                                   |
| ------- | -------------------------------------------------------------------- |
| 图像处理    | 从串口读取任务指令（`@...#` 格式），根据任务标识（`R`/`G`/`B`/`C`）执行物料颜色检测或圆环检测，将结果放入发送队列 |
| OLED 显示 | 读取拨码开关切换运行模式（`main`/`debug`），在 OLED 上显示当前模式、服务端 IP 及识别结果             |
| 图像传输    | 将处理后的图像通过 UDP 发送到客户端，调试模式是时直接发送原始图像                                  |

```bash
uv run main
```

***

### 3. `uv run setup color` — 颜色检测参数调试

打开 Trackbar 窗口，实时调整 HSV 颜色阈值（色相中心、容差、饱和度范围、明度范围、物料面积范围等），按 **`s`** 保存到 `config.yml`，按 **`q`** 退出。

| 参数         | 类型    | 默认值     | 说明                           |
| ---------- | ----- | ------- | ---------------------------- |
| `--remote` | flag  | `False` | 是否使用远程摄像头（图传接收）              |
| `--capip`  | `str` | `""`    | 远程摄像头 IP 地址，仅 `--remote` 时有效 |
| `--port`   | `int` | `None`  | 远程摄像头端口号，仅 `--remote` 时有效    |
| `--capid`  | `int` | `0`     | 本地摄像头设备 ID                   |

```bash
# 本地摄像头
uv run setup color --capid 0

# 远程图传
uv run setup color --remote --capip 192.168.1.100 --port 4444
```

***

### 4. `uv run setup colorring` — 色环检测参数调试

打开 Trackbar 窗口，实时调整色环检测的全部参数（腐蚀迭代次数、CLAHE 对比度、高斯模糊、形态学梯度、霍夫圆检测参数等），按 **`s`** 保存到 `config.yml`，按 **`q`** 退出。

| 参数         | 类型    | 默认值     | 说明                           |
| ---------- | ----- | ------- | ---------------------------- |
| `--remote` | flag  | `False` | 是否使用远程摄像头（图传接收）              |
| `--capip`  | `str` | `""`    | 远程摄像头 IP 地址，仅 `--remote` 时有效 |
| `--port`   | `int` | `None`  | 远程摄像头端口号，仅 `--remote` 时有效    |
| `--capid`  | `int` | `0`     | 本地摄像头设备 ID                   |

```bash
# 本地摄像头
uv run setup colorring --capid 0

# 远程图传
uv run setup colorring --remote --capip 192.168.1.100 --port 4444
```

***

### 5. `uv run img_trans` — 图像传输

无额外参数。根据操作系统平台自动切换模式：

| 平台      | 行为                                                 |
| ------- | -------------------------------------------------- |
| Linux   | 使用 `wlan0` 网卡在端口 `4444` 创建 UDP 图像发送器，持续从摄像头读取画面并发送 |
| Windows | 作为 UDP 图像接收器，从图传发送端接收画面并显示，按 `q` 退出                |

```bash
uv run img_trans
```

***

## 主要依赖

| 包名            | 说明          |
| ------------- | ----------- |
| opencv-python | 计算机视觉核心库    |
| numpy         | 数值计算        |
| pyserial      | 串口通信        |
| pyyaml        | YAML 配置文件解析 |
| loguru        | 日志记录        |
| click         | 命令行接口       |
| jieba         | 中文分词        |

***

## 配置文件

项目使用 `config.yaml` 存储颜色检测的 HSV 阈值参数，可通过 `setup color` 命令交互式调节并保存。

示例配置：

```yaml
color:
  R:
    centre: 0
    error: 17
    L_S: 80
    U_S: 255
    L_V: 20
    U_V: 255
  G:
    centre: 65
    error: 17
    ...
```

***

## 注意事项

1. **平台差异**：
   - Linux 环境下使用 `utils.Cap()` 初始化摄像头，并支持 GPIO、OLED、串口等硬件操作
   - Windows 环境下使用 `cv2.VideoCapture(0)`，不支持 GPIO 相关功能
2. **串口配置**：
   - 默认串口为 `/dev/ttyUSB0`，可在 `app.py` 中修改 `SERIAL_PORT`
3. **网络配置**：
   - 默认使用 `eth0` 网卡获取 IP，可在 `app.py` 中修改 `SERVER_INTERFACE`

***

## 许可证

本项目为内部比赛/项目使用，请遵循相关开源协议。
