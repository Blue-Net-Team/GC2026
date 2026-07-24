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

完整的泰山派刷机、WiFi、权限、开机自启部署流程见 [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)。设计模式与各项约定背后的原因见 [`docs/DESIGN.md`](docs/DESIGN.md)。

### 常见板端问题速查（可让 coding agent 直接登录板子操作）

- **apt 包被锁定无法安装/升级**：泰山派镜像默认 hold 了一批系统包。执行 `environments.sh` 第 13 行的 `sudo apt-mark unhold ...` 解锁后再 `apt-get install`。
- **WiFi 连不上**：先确认 WiFi 天线已安装。即使 `nmcli dev wifi list` 能扫到热点，`nmcli dev wifi connect` 输入正确密码也可能失败——此时不要反复重试，直接通过 adb 或 ssh 登录泰山派，在板子上手动执行 `nmcli dev wifi connect <SSID> password <密码>` 排查。
- **`/userdata` 目录权限不足**：程序需要在 `/userdata/code/GC2026` 下读写。让 `lckfb` 用户拥有该目录即可：`sudo chown -R lckfb:lckfb /userdata/code/GC2026`。
- **静态 IP、串口/GPIO 权限**：见 `docs/DEPLOYMENT.md`，包括 udev 规则与 `run_auto/*.service` 的启用方式。

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
| `uv sync` | 安装基础依赖（嵌入式主程序） |
| `uv sync --extra app` | 额外安装桌面应用依赖（PyQt6 等） |
| `uv sync --extra board` | 安装嵌入式 GPIO 依赖（periphery） |
| `uv run app` | 启动桌面调参应用（PyQt6，需先 `uv sync --extra app`） |
| `uv run main` | 启动嵌入式主程序（四个协程并行） |
| `uv run setup color --capid 0` | 颜色阈值调试工具（已废弃，优先用 `uv run app`） |
| `uv run setup colorring --capid 0` | 色环检测阈值调试工具（已废弃，优先用 `uv run app`） |
| `uv run img_trans` | 图像传输（Linux 发送 / Windows 接收） |

## 项目架构

### 协程模型

`main.py` 通过 `asyncio.gather` 并行运行四个协程：

1. **`main()`** — 图像处理主循环：从串口读取 `@...#` 格式任务指令（`R`/`G`/`B`/`C`/`F`），调用检测器处理，结果通过串口回写，处理后的图像写入 `img_need_to_send`。
2. **`board_show()`** — OLED 状态显示：读取拨码开关切换 `RUN_MODE`（`main`/`debug`），在 OLED 上显示当前模式、服务端 IP 及识别结果。
3. **`img_trans()`** — UDP 图传：将 `img_need_to_send` 通过 UDP 发送到客户端。`debug` 模式直接发送原始图像。
4. **`config_watcher()`** — 配置热加载：每秒计算 `config.yaml` 的 SHA-256，文件变化时调用 `Applications.reload_config()` 重载检测器参数，并同步更新 `system.udp_target_ip`。

### 任务字表（task_table）

`main.py` 中的 `task_table` 定义了串口任务字到应用层方法的映射：

| 任务字 | 调用方法 | 含义 |
|--------|----------|------|
| `R` / `G` / `B` | `applications.detect_material(img, color)` | 检测对应颜色色块/物料中心。**两个用途**：第一轮取料识别物料；第二轮码垛时以第一层物料颜色为基准定位——码垛高度下视野中有多个圆（圆环靶标 + 已码物料边缘），用 `C` 会返回错误圆环坐标，故码垛定位必须用颜色任务 |
| `C` | `applications.detect_circle(img, None)` | 检测地面色环靶标中心，仅在视野中无已码物料时使用（第一轮定位） |
| `F` | `refresh_img(img, None)` | 连续读取 5 帧刷新摄像头缓存，返回 `None`（回写 `FFFFFFFF`）；切换检测场景前由电控端先发送 |

### 串口协议速查

- 任务帧（电控 → 视觉）：`@<任务字>#`，115200 8N1；
- 结果帧（视觉 → 电控）：`@XXXXXXXX#` 定长 8 位，由 `Applications.tuple2str()` 编码——符号位（1 正 0 负）+ 3 位绝对值，x、y 各 4 位。例：`(12, -115)` → `10120115`；未识别到固定回 `FFFFFFFF`；
- 拨码开关：`read_status()` 为真 → `debug`（只发原始图，不响应串口），为假 → `main`；`system.switch_reverse` 适配接线电平。

### 给颜色检测器添加新颜色

以黄色 `Y` 为例，共 4 处改动（详见 README「task_table 与任务字扩展」一节）：

1. `config.yaml` 的 `color:` 段新增 `Y:` 阈值组（centre/error/L_S/U_S/L_V/U_V）；
2. `detector/ColorDetect.py`：`color_threshold` 加 `"Y"` 默认值、`TUNABLE_PARAMS.color_groups` 追加 `"Y"`（桌面应用会自动生成 Y Tab，`core/config_bridge.py` 默认配置也自动跟随）、`COLOR_DICT` 追加 `3: 'Y'` 并调大 `createTrackbar()` 中 color 滑条上限（如仍需使用已废弃的 `setup color`）；
3. `main.py` 的 `task_table` 注册 `"Y": (applications.detect_material, "Y")`；
4. 用 `uv run app`（推荐）调参后保存。

### 模块关系

```
main.py
├── applications.py          # 应用逻辑层，调度检测器
│   └── detector/
│       ├── ColorDetect.py   # TraditionalColorDetector（物料颜色检测）
│       ├── ColorRingDetect.py # ColorRingDetector（圆环检测）
│       ├── Detect.py        # 检测器基类（Tunable 接口 + visualize）
│       └── schema.py        # ParamDef / DetectorSchema 参数描述
├── core/
│   └── config_bridge.py     # SystemConfig / AppConfig，config.yaml 读写
├── utils/
│   ├── UART.py              # 串口通信（Uart 继承 serial.Serial，115200 8N1）
│   ├── gpio.py              # GPIO 抽象（LED / Switch / OLED_I2C）
│   ├── _cap.py              # 摄像头封装（Cap / InterpolatedCap / Mock 源）
│   ├── hardware_noop.py     # GPIO/OLED 初始化失败时的 no-op 占位
│   ├── file_hash.py         # SHA-256 文件 hash（配置热加载用）
│   └── ConfigLoader.py      # YAML 配置加载基类
└── ImgTrans/
    ├── IImgTrans.py         # 发送/接收接口基类
    └── ImgTrans.py          # TCP / UDP 图传实现
```

### 平台差异

- **Linux（开发板）**：使用 `utils.Cap()` 初始化摄像头（基于 v4l2，按 `system.camera_name` 匹配设备），支持 GPIO/OLED/串口硬件操作。通过 `periphery.GPIO` 操作泰山派 GPIO，引脚格式为 `"GPIO3-A2"`（芯片名-端口.引脚）。
- **Windows**：使用 `cv2.VideoCapture(0)`，GPIO 相关功能降级为空操作（`NoOpLED`、`NoOpSwitch`、`NoOpOLED`，见 `utils/hardware_noop.py`）。

### 配置

所有运行参数存储在 `config.yaml`：

- `system` 段：串口 `/dev/ttyS3`、UDP 端口/网卡/目标 IP、GPIO 引脚、OLED、摄像头名，由 `core/config_bridge.py` 的 `SystemConfig` 加载；
- `color` / `color_ring` 段：检测阈值，推荐通过 `uv run app` 交互式调节并保存；`uv run setup color` / `uv run setup colorring` 已废弃但仍兼容。
- 顶层全局参数：`min_material_area`、`max_material_area`（物料面积过滤，运行时使用）；`need2cut_height`、`target_angle`（**仅持久化，运行时未消费**，为画面裁剪/偏航角补偿预留）。

`config.yaml` 支持热加载：主程序运行期间修改后约 1 秒内自动生效（检测器参数 + `udp_target_ip`），无需重启。

### 事件循环阻塞注意事项

本项目重度依赖 `asyncio`，以下操作会阻塞事件循环，必须在线程中执行：

- **串口读取**（`UART.py`）：`serial.Serial.read()` 是阻塞的，整包读取应在线程中完成，通过 `asyncio.Future` 回调结果。
- **图像编码**（`ImgTrans/ImgTrans.py`）：`cv2.imencode('.jpg', ...)` 是 CPU 密集型操作。
- **GPIO / OLED 操作**（`utils/gpio.py`）：`OLED_I2C.text()` 和 `display()` 涉及 I2C 通信和 PIL 绘制，应通过 `run_in_executor` 执行。
- **摄像头读取**（`utils/_cap.py`）：`Cap.read()` 继承自 `cv2.VideoCapture`，虽已在主循环中同步调用，但在协程环境中仍需注意帧率对齐。

`Uart.new_read()` 和 `Uart.new_write()` 提供异步包装。修改这些函数时，避免在协程中直接调用同步阻塞的 `super().read()` / `super().write()`。
