# GC2026 桌面调参应用开发规范

> **适用范围**：`app/` 包、`app.py` 入口及其相关资源文件。
> **目标**：统一桌面端（PyQt6）代码结构、命名与启动方式，使其与现有 `uv run main/setup/img_trans` 保持一致。

---

## 1. 项目定位

桌面应用是 GC2026 的**辅助调参工具**，不替代嵌入式主程序 `main.py`，而是：

- 通过 UDP 接收开发板图传画面；
- 可视化调节 `config.yaml` 中的颜色 / 色环参数；
- 通过 SSH 部署配置、管理服务、查看日志。

启动入口统一使用：

```bash
uv run app
```

---

## 2. 目录结构

```
GC2026/
├── app.py                          # 桌面应用入口，暴露 cli() 给 uv
├── pyproject.toml                  # 已配置 app = "app:cli"
├── app/                            # 桌面应用主包
│   ├── __init__.py                 # 版本号、包级常量
│   ├── main.py                     # QApplication 与主窗口装配
│   ├── application.py              # 全局应用状态（单例，可选）
│   │
│   ├── core/                       # 非 UI 核心逻辑
│   │   ├── __init__.py
│   │   ├── udp_receiver.py         # UDP 图传接收
│   │   ├── frame_assembler.py      # 分片帧重组
│   │   ├── connection_manager.py   # UDP + SSH 连接状态管理
│   │   ├── ssh_client.py           # SSH 客户端封装
│   │   ├── service_manager.py      # systemd 服务控制
│   │   └── log_stream.py           # journalctl 日志流
│   │
│   ├── models/                     # 数据模型（纯 dataclass）
│   │   ├── __init__.py
│   │   ├── device.py               # RemoteDevice
│   │   ├── config.py               # AppConfig / ColorConfig / ColorRingConfig
│   │   ├── connection_state.py     # ConnectionState 枚举
│   │   ├── service_status.py       # ServiceStatus / ServiceState
│   │   └── log_entry.py            # LogEntry / LogLevel
│   │
│   ├── repositories/               # 数据持久化
│   │   ├── __init__.py
│   │   ├── device_repository.py    # 设备列表 JSON 存取
│   │   ├── config_repository.py    # config.yaml 读写
│   │   └── credential_store.py     # 凭据存储占位（当前明文 JSON，可后续升级）
│   │
│   ├── vision/                     # 图像处理适配层
│   │   ├── __init__.py
│   │   ├── color_tuner.py          # TraditionalColorDetector 包装
│   │   └── color_ring_tuner.py     # ColorRingDetector 包装
│   │
│   ├── ui/                         # UI 层
│   │   ├── __init__.py
│   │   ├── main_window.py          # 主窗口 / 导航 / 布局适配
│   │   ├── theme.py                # 单一深色主题 QSS
│   │   ├── widgets/                # 可复用控件
│   │   │   ├── __init__.py
│   │   │   ├── video_label.py      # 图传画面显示 QLabel
│   │   │   ├── param_slider.py     # 参数滑动条（QSlider + QSpinBox）
│   │   │   ├── color_tab_bar.py    # R/G/B 切换 Tab
│   │   │   ├── param_group_tab.py  # 色环参数分组 Tab
│   │   │   ├── status_panel.py     # FPS / 丢包 / 连接状态
│   │   │   ├── connection_bar.py   # 设备选择与连接控制
│   │   │   ├── device_card.py      # 设备列表卡片
│   │   │   ├── device_edit_dialog.py
│   │   │   ├── service_control_card.py
│   │   │   └── log_terminal.py     # 日志终端显示
│   │   └── screens/                # 六大模式页面
│   │       ├── __init__.py
│   │       ├── receiver_screen.py
│   │       ├── color_screen.py
│   │       ├── color_ring_screen.py
│   │       ├── log_screen.py
│   │       ├── config_screen.py
│   │       └── service_screen.py
│   │
│   ├── utils/                      # 应用专属工具
│   │   ├── __init__.py
│   │   ├── debounce.py             # 滑动条防抖
│   │   └── yaml_serializer.py      # YAML 序列化辅助
│   │
│   └── resources/                  # 静态资源
│       ├── icons/
│       ├── fonts/
│       └── styles/
│
├── docs/
│   ├── PRD-App.md                  # 产品需求文档
│   ├── app.pen                     # Pencil 设计稿
│   └── APP_DEV_SPEC.md             # 本文件
```

---

## 3. 命名规则

### 3.1 文件与包名

| 类型 | 规则 | 示例 |
|------|------|------|
| 包名 | 小写、下划线分隔 | `app`, `core`, `vision` |
| 模块文件 | 小写、下划线分隔 | `udp_receiver.py`, `param_slider.py` |
| 类名 | 大驼峰 | `UdpImgReceiver`, `MainWindow` |
| 函数 / 方法 | 小写、下划线分隔 | `start_receive()`, `on_slider_changed()` |
| 常量 | 全大写 | `CHUNK_MAX_SIZE`, `DEFAULT_SSH_PORT` |
| 私有成员 | 单下划线前缀 | `_worker_thread`, `_last_frame` |
| PyQt 信号 | 小驼峰 | `frameReceived`, `connectionStateChanged` |

### 3.2 UI 控件变量名

控件类型后缀建议：

| 控件类型 | 后缀 | 示例 |
|----------|------|------|
| QPushButton | `_btn` | `save_btn`, `connect_btn` |
| QSlider | `_slider` | `centre_slider` |
| QSpinBox / QDoubleSpinBox | `_spin` | `centre_spin` |
| QLabel | `_label` | `fps_label` |
| QLineEdit | `_edit` | `ip_edit` |
| QComboBox | `_combo` | `device_combo` |
| QGroupBox | `_group` | `ssh_group` |
| QWidget | `_widget` | `preview_widget` |

### 3.3 信号与槽

- 信号名使用 `pyqtSignal` 定义，名称形如 `frameReceived`。
- 槽函数统一以 `on_` 开头，事件源明确：
  - `on_connect_btn_clicked()`
  - `on_centre_slider_changed(value: int)`
  - `on_device_selected(index: int)`

---

## 4. 启动约定

### 4.1 入口文件 `app.py`

`app.py` 位于项目根目录，仅做入口委托：

```python
import sys
import click
from app.main import main

@click.command()
@click.option("--debug", is_flag=True, help="启用调试日志")
def cli(debug: bool) -> None:
    """启动 GC2026 桌面调参应用"""
    sys.exit(main(debug=debug))

if __name__ == "__main__":
    cli()
```

### 4.2 `pyproject.toml` 配置

```toml
[project.scripts]
main = "main:cli"
setup = "setup:cli"
img_trans = "img_trans:cli"
app = "app:cli"
```

### 4.3 运行方式

```bash
# 直接启动桌面应用
uv run app

# 调试模式
uv run app --debug
```

---

## 5. 技术栈

| 层级 | 选型 | 说明 |
|------|------|------|
| UI 框架 | PyQt6 | 主窗口、信号槽、多线程 |
| Qt 事件循环桥接 | qasync | 让 Qt 事件循环兼容 asyncio，支持 `await` 现有识别函数 |
| 图像处理 | OpenCV-Python | 复用 `detector/` 已有检测器 |
| 网络 | 标准库 `socket` | UDP 图传接收 |
| SSH | paramiko | 远程命令 / 文件传输 / 日志流 |
| 凭据存储 | 本地 JSON（明文） | 当前阶段不引入 keyring，后续可按需升级 |
| 配置序列化 | PyYAML | 兼容 `config.yaml` |
| 日志 | loguru | 与项目其他模块保持一致 |
| CLI 入口 | click | 与 `main/setup/img_trans` 保持一致 |

---

## 6. 异步与线程规范

### 6.1 核心策略

使用 **`qasync` 作为事件循环桥接**，耗时操作通过 `run_in_executor()` 放到线程池执行。

```python
import asyncio
import qasync
from PyQt6.QtWidgets import QApplication

async def main():
    app = QApplication(sys.argv)
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    window = MainWindow()
    window.show()

    with loop:
        await loop.run_forever()
```

### 6.2 各模块执行位置

| 任务 | 执行位置 | 与 UI 通信方式 |
|------|----------|----------------|
| UDP 接收 | 独立 `QThread` | `pyqtSignal` 发帧 |
| OpenCV 图像处理 | `run_in_executor()` 线程池 | `await` 返回结果后更新 UI |
| SSH 命令 / 文件传输 | `run_in_executor()` 线程池 | `await` 返回结果后更新 UI |
| 日志流 | 独立 `QThread` 读 SSH channel | `pyqtSignal` 逐行发送 |

### 6.3 禁止行为

- 禁止在主线程直接 `await` CPU 密集型协程（如 `detector.binarization()`）。
- 禁止在主线程执行 `socket.recvfrom()` 阻塞读取。
- 禁止在 `QThread` 中直接操作 UI 控件（必须通过信号）。

### 6.4 `vision/` 包装示例

```python
# app/vision/color_tuner.py
import asyncio
import cv2
import numpy as np
from detector import TraditionalColorDetector

class ColorTuner:
    def __init__(self):
        self.detector = TraditionalColorDetector()

    def process(self, frame: np.ndarray, color: str) -> tuple[np.ndarray, np.ndarray, tuple | None]:
        """同步包装，供 run_in_executor 调用"""
        self.detector.update_threshold(color)
        mask = asyncio.run(self.detector.binarization(frame))
        position = asyncio.run(self.detector.get_color_position(mask))

        annotated = frame.copy()
        if position is not None:
            cx, cy, w, h = position
            cv2.rectangle(annotated, (cx - w // 2, cy - h // 2), (cx + w // 2, cy + h // 2), (0, 255, 0), 2)

        return annotated, mask, position
```

UI 层调用：

```python
annotated, mask, position = await asyncio.get_event_loop().run_in_executor(
    None, self.tuner.process, frame, self.current_color
)
self.update_preview(annotated, mask)
```

---

## 7. 主题

仅保留**单一深色主题**，不实现浅色切换。

- 颜色常量定义在 `app/ui/theme.py`。
- QSS 主样式集中管理，避免散落在各控件中。

---

## 8. 配置兼容

桌面应用必须读写 GC2026 现有的 `config.yaml`，格式如下：

```yaml
color:
  R:
    centre: 0
    error: 12
    L_S: 41
    U_S: 255
    L_V: 29
    U_V: 255
  G: { ... }
  B: { ... }

color_ring:
  erode_iter: 1
  dilate_kernel_size: 5
  clahe_clip_limit: 1.2
  clahe_tile_size: 8
  morph_kernel_size: 3
  gaussian_kernel_size: 9
  gaussian_sigma: 1.5
  alpha: 4.4
  threshold_value: 34
  hough_dp: 0.9
  hough_min_dist: 68
  hough_param1: 72
  hough_param2: 100
  min_radius: 54
  max_radius: 281
  expected_circles: 5

min_material_area: 5940
max_material_area: 300000
need2cut_height: 0
target_angle: 46
```

- 颜色调参仅修改 `color` 与 `min_material_area` / `max_material_area`。
- 色环调参仅修改 `color_ring`。
- 导出时必须保留其他字段，禁止覆盖丢失。

---

## 9. UI 实现顺序

分三阶段实现，先跑通功能再细化美化：

1. **第一阶段**：标准控件搭出 6 个页面和布局，能跑通 UDP 接收 + 颜色调参保存。
2. **第二阶段**：按 `docs/app.pen` 设计稿做 QSS 美化、自定义滑动条、DeviceCard 卡片。
3. **第三阶段**：SSH、服务管理、日志流、配置部署。

---

## 10. 代码提交与新增文件规范

1. 新增 `.py` 文件顶部保留项目 GPL 声明（参考 `detector/` 现有文件）。
2. 中文注释优先，代码标识符使用英文。
3. 类型注解：Python 3.12+，支持 `|` 联合类型。
4. 不引入新的包管理器或构建工具，统一使用 `uv`。
5. UI 改动需对照 `docs/app.pen` 设计稿，截图存 `docs/screenshots/`。

---

## 11. 与现有模块的关系

```
app.py
└── app/
    ├── vision/
    │   └── 调用 detector.ColorDetect / ColorRingDetect
    ├── core/
    │   ├── udp_receiver.py  参考 ImgTrans.ReceiveImgUDP
    │   └── config_repository.py 参考 utils.ConfigLoader
    └── ui/
        └── 按 docs/app.pen 实现界面
```

---

## 12. 附录：新增依赖

在 `pyproject.toml` 中追加：

```toml
dependencies = [
    # 已有依赖 ...
    "pyqt6>=6.9.0",
    "qasync>=0.27.1",
    "paramiko>=3.5.1",
]
```

之后执行：

```bash
uv add pyqt6 qasync paramiko
```

或手动修改后运行 `uv sync`。
