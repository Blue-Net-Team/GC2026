# GC2026 开发手册

> 本文档面向 GC2026 的维护者与贡献者，说明项目的整体架构、识别器（Detector）开发契约，以及如何在不破坏现有功能的前提下添加新功能。
>
> 若你只关心桌面调参应用（`app/`）的 UI 规范，请先看 [`APP_DEV_SPEC.md`](./APP_DEV_SPEC.md)。

---

## 1. 项目定位

GC2026 的运行时核心分为三层：

- **main 层**（`main.py`）：程序入口与事件循环，负责编排图像处理、OLED 显示、UDP 图传三个协程；读取串口任务、调用应用层、回传结果、准备图传图像。
- **应用层**（`applications.py`）：业务调度器，根据任务字调用识别器，并把识别结果转换为对外格式。
- **基础设施层**（`utils/`、`ImgTrans/`、`detector/`）：提供硬件抽象、UDP 图传、配置加载、视觉算法等可复用能力。

此外，项目还有两个**调参工具**：

- **`setup.py`**：基于 OpenCV Trackbar 的命令行调参工具；
- **`app/`**：基于 PyQt6 的桌面调参应用，可动态渲染识别器调参页面。

调参工具直接调用基础设施中的识别器来调试参数、生成 `config.yaml`，但它们本身不参与 `main.py` 的运行时任务闭环。

---

## 2. 三层架构

运行时核心按职责划分为三层：

| 层级 | 代表文件/目录 | 主要职责 |
|------|---------------|----------|
| **main 层** | `main.py` | 事件循环、协程编排、串口任务读取、结果回传、图传图像准备 |
| **应用层** | `applications.py` | 按任务字调度识别器、处理识别结果、转换为对外格式 |
| **基础设施层** | `utils/`、`ImgTrans/`、`detector/` | 硬件抽象、通信、配置加载、视觉算法等可复用能力 |

```
        调参工具
   ┌─────────────────┐
   │  app/  | setup  │
   │  调参界面/Trackbar│
   └────────┬────────┘
            │ 调用识别器接口
            ▼
   ┌─────────────────────────────┐
   │        基础设施层            │
   │  ┌─────────────────────┐    │
   │  │   detector/         │    │
   │  │   算法基础设施       │    │
   │  │  TUNABLE_PARAMS     │    │
   │  │  detect()           │    │
   │  └─────────────────────┘    │
   │  ┌─────────────────────┐    │
   │  │      utils/         │    │
   │  │  硬件/配置基础设施   │    │
   │  └─────────────────────┘    │
   │  ┌─────────────────────┐    │
   │  │    ImgTrans/        │    │
   │  │    通信基础设施      │    │
   │  └─────────────────────┘    │
   └─────────────┬───────────────┘
                 │
                 ▼
   ┌─────────────────────────────┐
   │        应用层                │
   │    applications.py           │
   │  按任务字调度识别器并处理结果  │
   └─────────────┬───────────────┘
                 │
                 ▼
   ┌─────────────────────────────┐
   │        main 层               │
   │       main.py                │
   │  串口读取 → 调用应用层 → 回传  │
   │  准备图传图像 / OLED 显示      │
   └─────────────────────────────┘
```

### 2.1 各层职责

| 层级 | 主要职责 | 禁止行为 |
|------|----------|----------|
| **main 层** | 协程编排、串口读取、通过 `TASK_TABLE` 选择应用层方法、结果回传、图传/OLED 准备 | 包含视觉算法细节；直接实例化并调用识别器（应通过 `Applications`） |
| **应用层** | 提供按任务类型封装的业务方法、调用识别器、结果格式化、识别器实例管理 | 决定“哪个任务字调用谁”（由 `main.py` 的 `TASK_TABLE` 决定）；直接写死识别器内部算法参数；直接操作串口/GPIO/网络 |
| **基础设施层** | 提供硬件、通信、算法等可复用能力 | 包含业务判断逻辑；跨层依赖 UI 框架 |
| **调参工具** | 调用识别器接口调试参数、持久化 `config.yaml` | 在嵌入式运行时中直接参与任务闭环 |

### 2.2 main 层与应用层的区别

- **main 层**只关心“有没有任务、任务交给谁、结果怎么发、图传怎么送”。它通过 `TASK_TABLE` 把任务字映射到 `Applications` 的方法，但并不知道 `detect_material` 内部用的是 HSV 还是霍夫圆。
- **应用层**关心“这个任务该用哪个识别器、结果坐标怎么转换、可视化图像怎么拼”。它持有识别器实例，是识别器与 main 层之间的唯一接口。

### 2.3 调用关系

#### 运行时调用链

1. `main.py` 通过 `Uart` 读取 `@...#` 任务字；
2. 根据 `TASK_TABLE` 调用 `applications.py` 中的对应方法；
3. `Applications` 调用识别器的 `detect()` 和 `visualize()`，得到 `(coord, draw_img)`；
4. `main.py` 把坐标写回串口，把 `draw_img` 交给 `img_trans()` 发送。

#### TASK_TABLE 与任务字扩展

`main.py` 中的 `TASK_TABLE` 是“串口任务字 → 应用层方法”的唯一映射表：

```python
TASK_TABLE = {
    "R": (applications.detect_material, "R"),
    "G": (applications.detect_material, "G"),
    "B": (applications.detect_material, "B"),
    "C": (applications.detect_circle, None),
}
```

每个条目是一个二元组：

- 第 1 个元素：`Applications` 的方法对象（函数指针）；
- 第 2 个元素：调用时传入的附加参数（如颜色标签），不需要时传 `None`。

`main()` 协程中的实际调用代码为：

```python
res, res_img = await TASK_TABLE[task_sign][0](
    img, TASK_TABLE[task_sign][1]
)
```

**应用层方法签名要求**

被 `TASK_TABLE` 指向的方法必须满足以下约定：

- 必须是协程：`async def ...`，因为 `main.py` 使用 `await` 调用；
- 第一个参数为 `self`；
- 第二个参数为 `img: cv2.typing.MatLike`，即当前帧原始图像；
- 第三个参数（可选）用于接收 `TASK_TABLE` 中的附加参数，建议写成 `label=None` 并给默认值；
- 返回值必须是二元组 `(coord, draw_img)`：
  - `coord`：识别到的坐标，传 `None` 表示未识别到，或传 `(x, y)` 元组；`main.py` 会把它交给 `Applications.tuple2str()` 转换成固定长度字符串后写回串口；
  - `draw_img`：`np.ndarray` 类型可视化图像，会被 `main.py` 放入 `img_need_to_send` 通过 UDP 发送给客户端。

示例签名：

```python
async def detect_my_target(
    self,
    img: cv2.typing.MatLike,
    label=None,
) -> tuple[tuple[int, int] | None, np.ndarray]:
    ...
    return (cx, cy), draw_img
```

**新增一个任务字的标准流程**：

1. 在 `applications.py` 的 `Applications` 类中新增业务方法，约定返回 `(coord, draw_img)`：
   ```python
   async def detect_my_target(self, img: cv2.typing.MatLike, label=None):
       result, binary = await self.myDetector.detect(img)
       draw_img = self.myDetector.visualize(img, result, binary)
       if result is None:
           return None, draw_img
       return (result[0], result[1]), draw_img
   ```
2. 在 `Applications.__init__()` 中实例化并加载新识别器：
   ```python
   self.myDetector = MyDetector()
   self.myDetector.load_config(config_path)
   ```
3. 在 `main.py` 的 `TASK_TABLE` 中新增映射：
   ```python
   TASK_TABLE = {
       ...
       "M": (applications.detect_my_target, None),
   }
   ```
4. 如果新识别器需要桌面调参页面，在 `app/ui/main_window.py` 的 `DETECTOR_REGISTRY` 中注册。

> **注意**：任务字 → 方法的映射**只能**放在 `main.py` 的 `TASK_TABLE`，应用层只负责提供可调用的业务方法，不能自行决定响应哪些任务字。

#### 调参调用链

1. `MainWindow` 根据 `DETECTOR_REGISTRY` 为每个识别器创建 `DetectorTunerScreen`；
2. `DetectorTunerScreen` 实例化识别器，调用 `load_tunable_from_app_config()`；
3. 根据 `tunable_schema()` 动态渲染滑条；
4. 用户拖动滑条 → `set_tunable_value()` → debounce → `detect()` → `draw_overlay()` / `format_detection_info()`；
5. 用户保存 → `save_tunable_to_app_config()` → `ConfigBridge.save()`。

### 2.4 数据流示例（调参页面）

1. `ConfigBridge` 从 `config.yaml` 加载配置；
2. `DetectorTunerScreen` 创建识别器实例，调用 `load_tunable_from_app_config()` 写入当前值；
3. 用户拖动滑条 → UI 调用 `set_tunable_value(key, value, section)`；
4. 300 ms debounce 后，UI 调用 `detect(frame)` 得到 `(result, binary)`；
5. UI 调用 `draw_overlay()` 和 `format_detection_info()` 更新上侧预览与信息区；
6. 用户点击“保存” → UI 调用 `save_tunable_to_app_config()`，再由 `ConfigBridge.save()` 落盘。

---

## 3. 识别器（Detector）是什么

**识别器是基础设施层中封装了单一视觉任务的算法单元**。它本身不持有业务状态、不参与任务调度，只是被应用层 `applications.py` 和调参工具调用的“算法服务”。在 GC2026 中，它同时向两类消费者提供服务：

- **运行时消费者**：`applications.py` 在串口任务到来时调用它，得到坐标和可视化图像；
- **调参消费者**：`app/` 和 `setup.py` 读取它的参数定义，动态生成滑条和预览界面。

因此，识别器必须是**自描述、自读写、自预览、自持久化**的：

- **自描述**：通过 `TUNABLE_PARAMS` 告诉外部自己有哪些可调参数、范围、分组；
- **自读写**：通过 `get_tunable_value` / `set_tunable_value` 等接口，让外部不需要知道参数存在类属性还是嵌套字典里；
- **自预览**：通过 `detect()` / `draw_overlay()` / `format_detection_info()` 输出可拼接的预览图和文字信息；
- **自持久化**：通过 `load_config()` / `save_config()` 与 `config.yaml` 交互。

项目中已有的识别器：

| 文件 | 类 | 任务 | 参数形态 |
|------|-----|------|----------|
| `detector/ColorDetect.py` | `TraditionalColorDetector` | 物料颜色检测 | 按颜色分组 `R/G/B` + 全局参数 |
| `detector/ColorRingDetect.py` | `ColorRingDetector` | 地面色环检测 | 按处理阶段分组 `预处理/霍夫检测/后处理` |

---

## 4. 识别器开发契约

### 4.1 必须遵守的接口

新建识别器必须继承 `Detect`（`detector/Detect.py`），并至少实现以下接口：

```python
class MyDetector(Detect):
    # 1. 声明可调参数 schema
    TUNABLE_PARAMS = DetectorSchema(...)

    # 2. 参数读写（平铺参数可沿用基类默认实现）
    def get_tunable_value(self, key: str, section: str | None = None) -> Any: ...
    def set_tunable_value(self, key: str, value: Any, section: str | None = None) -> None: ...
    def load_tunable_from_app_config(self, app_config: AppConfig) -> None: ...
    def save_tunable_to_app_config(self, app_config: AppConfig) -> None: ...

    # 3. 预览/运行时接口（必须实现）
    async def detect(self, frame: np.ndarray) -> tuple[Any, np.ndarray]: ...
    def draw_overlay(self, frame: np.ndarray, result: Any, binary: np.ndarray) -> np.ndarray: ...
    def format_detection_info(self, result: Any) -> str: ...

    # 4. 配置持久化（可选但推荐）
    def load_config(self, config: str | dict): ...
    def save_config(self, path: str): ...
```

`Detect` 基类已经提供了默认的 `visualize()`，会把 `draw_overlay()` 的输出与 `binary` 纵向拼接，供 `applications.py` 直接调用。如果你的可视化逻辑比较特殊，可以覆盖它。

### 4.2 参数 Schema 详解

`detector/schema.py` 定义了 `ParamDef` 和 `DetectorSchema`：

```python
@dataclass
class ParamDef:
    key: str                  # 识别器实例上的属性名 / 配置文件 key
    label: str                # UI 显示的中文名
    param_type: "int" | "float"
    min: float                # UI 最小值
    max: float                # UI 最大值
    step: float = 1.0         # UI 步长
    decimals: int = 0         # 浮点数显示位数
    odd_only: bool = False    # 是否强制奇数（卷积核）
    scale: float = 1.0        # UI 值 → 实际值的倍数
    group: str | None = None  # 色环分组："预处理" / "霍夫检测" / "后处理"
    section: str | None = None  # 颜色分组："global" 或颜色名
```

`DetectorSchema` 支持三种布局：

| 布局 | 触发条件 | 适用场景 |
|------|----------|----------|
| **color-tabs** | `color_groups` 非空 | 颜色检测，每个颜色一组参数，外加 `section="global"` 的全局参数 |
| **group-tabs** | `groups` 非空 | 色环检测，参数按处理阶段分 Tab |
| **flat** | 两者皆空 | 简单识别器，所有参数平铺在一个面板 |

> **注意**：
> - `color_groups` 用于颜色类参数；颜色共用的全局参数用 `section="global"` 标记。
> - `groups` 用于色环等按流程分组的参数；每个 `ParamDef` 用 `group` 字段归属到对应 Tab。
> - `section` 与 `group` 不要混用：UI 在 `color-tabs` 下才会按 `section` 查找参数定义。

### 4.3 完整模板

```python
# detector/my_detector.py
import cv2
import numpy as np
from loguru import logger
from .Detect import Detect
from .schema import DetectorSchema, ParamDef

_log = logger.bind(module="MyDetector")


class MyDetector(Detect):
    """
    示例识别器：检测画面中的最大轮廓并返回其外接矩形。
    ----
    实际算法请根据赛题需求替换。
    """

    # 类属性 = 实际运行时默认值
    threshold: int = 128
    min_area: int = 1000

    # UI 参数声明
    TUNABLE_PARAMS = DetectorSchema(
        name="my_detector",          # 对应 config.yaml 顶层 key
        params=[
            ParamDef("threshold", "二值化阈值", "int", 0, 255),
            ParamDef("min_area", "最小面积", "int", 0, 5000, scale=10),
        ],
    )

    async def detect(self, frame: np.ndarray) -> tuple[tuple[int, int, int, int] | None, np.ndarray]:
        """返回 (result, binary)，result 可以是任意类型。"""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(gray, self.threshold, 255, cv2.THRESH_BINARY)

        contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return None, binary

        largest = max(contours, key=cv2.contourArea)
        if cv2.contourArea(largest) < self.min_area:
            return None, binary

        x, y, w, h = cv2.boundingRect(largest)
        cx, cy = x + w // 2, y + h // 2
        return (cx, cy, w, h), binary

    def draw_overlay(
        self,
        frame: np.ndarray,
        result: tuple[int, int, int, int] | None,
        binary: np.ndarray,
    ) -> np.ndarray:
        """上侧预览：原图 + 检测标记。"""
        output = frame.copy()
        if result is not None:
            cx, cy, w, h = result
            x1, y1 = cx - w // 2, cy - h // 2
            x2, y2 = cx + w // 2, cy + h // 2
            cv2.rectangle(output, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.circle(output, (cx, cy), 4, (0, 255, 0), -1)
        return output

    def format_detection_info(self, result: tuple[int, int, int, int] | None) -> str:
        """右侧检测信息卡文本。"""
        if result is None:
            return "未检测到目标"
        cx, cy, w, h = result
        return f"目标: ({cx}, {cy}) 外接矩形: {w}x{h}"

    def save_config(self, path: str):
        config = super().load_config(path)
        config["my_detector"] = {
            "threshold": self.threshold,
            "min_area": self.min_area,
        }
        super().save_config(path, config)

    def load_config(self, config: str | dict):
        config_dict = super().load_config(config)
        try:
            section = config_dict["my_detector"]
        except KeyError:
            _log.warning(f"配置文件中没有 my_detector 配置项，使用默认值")
            return

        super().load_param(section, "threshold", default=self.threshold)
        super().load_param(section, "min_area", default=self.min_area)

        # 配置文件中可能保存为 float，按 schema 把 int 参数转回整数
        for param in self.tunable_schema().params:
            if param.param_type == "int":
                setattr(self, param.key, int(round(getattr(self, param.key))))
```

### 4.4 默认值该在哪里改

识别器的**默认值就是源码里的类属性**（以及 `color_threshold` 等嵌套字典）。

- 修改 `TraditionalColorDetector.color_threshold["R"]["centre"]` 会同时影响：
  - 没有配置文件时的首次运行默认值；
  - 桌面端 `ConfigBridge` 推导出的默认配置；
  - “恢复默认”按钮恢复的值。
- 修改 `ColorRingDetector.erode_iter` 等类属性同理。

因此，**所有默认参数统一在识别器源码中维护**，不要分散写在 `config_bridge.py` 或 UI 里。

---

## 5. 把新识别器接入桌面应用

### 5.1 注册到导航栏

打开 `app/ui/main_window.py`，在 `DETECTOR_REGISTRY` 中添加一行：

```python
from detector.my_detector import MyDetector

DETECTOR_REGISTRY: list[tuple[type, str, str, str, bool]] = [
    (TraditionalColorDetector, "颜色调参", "palette", "RGB.svg", True),
    (ColorRingDetector, "色环调参", "donut_large", "圆环.svg", False),
    (MyDetector, "我的识别器", "camera", "my_icon.svg", False),
]
```

字段含义：

| 字段 | 说明 |
|------|------|
| `detector_cls` | 识别器类 |
| `title` | 侧边栏与页面标题 |
| `fallback_icon` | 当图标文件缺失时使用的 Material Symbols 图标名 |
| `icon_file` | `app/resources/icons/` 下的图标文件名 |
| `colored` | `True` 表示使用图标原始颜色，`False` 表示按主题色着色 |

### 5.2 接入配置文件（可选）

如果你的识别器需要把参数持久化到 `config.yaml`，需要扩展 `app/core/config_bridge.py` 中的 `AppConfig`：

```python
@dataclass
class AppConfig:
    color: dict[str, ColorConfig] = field(default_factory=...)
    color_ring: dict[str, Any] = field(default_factory=...)
    my_detector: dict[str, Any] = field(default_factory=_default_my_detector_params)
    ...
```

并添加 `_default_my_detector_params()` 从 `MyDetector` 的 schema/类属性推导默认值。

如果识别器参数不需要持久化（例如完全运行时计算），可跳过此步。

### 5.3 接入嵌入式主程序

在 `applications.py` 中新增调度方法：

```python
async def detect_my_target(self, img: cv2.typing.MatLike):
    result, binary = await self.myDetector.detect(img)
    draw_img = self.myDetector.visualize(img, result, binary)
    if result is None:
        return None, draw_img
    cx, cy, w, h = result
    return (cx, cy), draw_img
```

然后在 `main.py` 的 `TASK_TABLE` 中注册任务字：

```python
TASK_TABLE = {
    "R": (applications.detect_material, "R"),
    "G": (applications.detect_material, "G"),
    "B": (applications.detect_material, "B"),
    "C": (applications.detect_circle, None),
    "M": (applications.detect_my_target, None),
}
```

---

## 6. 添加非识别器的新功能页面

如果新功能不需要调参页面（例如新的日志视图、新的统计面板），按以下步骤：

1. 在 `app/ui/screens/` 新建 `xxx_screen.py`，继承 `QWidget`；
2. 在 `MainWindow.__init__` 中实例化该页面；
3. 在 `nav_items` 列表中添加导航项（图标、标题、图标文件路径、是否彩色）；
4. 用 `self._stack.addWidget(...)` 加入堆叠窗口；
5. 在 `_on_screen_changed()` 中处理切页刷新逻辑。

---

## 7. 开发规范与常见陷阱

### 7.1 识别器层

- **不要引入 PyQt6**：`detector/` 只能依赖 `cv2`、`numpy`、`loguru` 等通用库。
- **参数类型安全**：UI 滑条传回的值是 `float`，必须在 `set_tunable_value` 中把 `param_type == "int"` 的参数截断为整数。基类已实现默认逻辑，若覆盖请勿遗漏。
- **不要阻塞事件循环**：`detect()` 是协程，但内部若调用长时间 `cv2` 操作，仍可能阻塞 `asyncio` 事件循环。耗时操作应通过 `run_in_executor` 放到线程池。
- **返回一致性**：`detect()` 必须始终返回 `(result, binary)`，其中 `binary` 是单通道灰度/二值图或三通道图，用于下侧预览。

### 7.2 UI 层

- **禁止在主线程直接执行耗时 OpenCV 运算**：`DetectorTunerScreen` 已经把 `detect()` 放到 `ThreadPoolExecutor`，新增页面请保持同样做法。
- **线程安全**：`QThread` 中不要直接操作 QWidget；通过 `pyqtSignal` 更新界面。
- **不要写死参数**：所有调参页面都应基于 `DetectorSchema` 动态渲染。

### 7.3 配置与默认值

- `config.yaml` 是 GC2026 嵌入式端与桌面端的共同配置，新增字段时要保持向后兼容。
- 默认值来源单一：识别器源码类属性 → `ConfigBridge` 推导 → UI 显示。
- 保存配置时先读取原文件再覆盖，避免丢失未显示的字段（参考 `Detect.save_config` 的做法）。

### 7.4 常见错误

| 现象 | 原因 | 解决 |
|------|------|------|
| 调参页面滑动后报错 `Argument 'iterations' is required to be an integer` | `int` 参数被 UI 以 `float` 写入 | 确保 `set_tunable_value` 按 schema 截断为 `int` |
| 色环参数调整无效 | 把 `group` 名误当作 `section` 传给 `set_tunable_value` | group-tabs/flat 下传 `section=None` |
| 新增识别器后侧边栏没出现 | 未加入 `DETECTOR_REGISTRY` 或导入失败 | 检查 `main_window.py` 注册表与导入路径 |
| 恢复默认后数值不对 | 默认值分散在多处 | 统一改识别器类属性 |

---

## 8. 调试与验证

### 8.1 快速验证识别器契约

```python
import asyncio
import cv2
from detector.my_detector import MyDetector

async def main():
    d = MyDetector()
    schema = d.tunable_schema()
    print("schema:", schema.name, [p.key for p in schema.params])

    frame = cv2.imread("test.jpg")
    result, binary = await d.detect(frame)
    overlay = d.draw_overlay(frame, result, binary)
    info = d.format_detection_info(result)
    print(info)
    cv2.imwrite("overlay.jpg", overlay)

asyncio.run(main())
```

### 8.2 桌面端验证

```bash
uv sync --extra app
uv run --extra app app
```

检查：

- 侧边栏出现新识别器入口；
- 上侧为 `draw_overlay()` 输出，下侧为 `binary`；
- 滑动条调整后 300 ms 预览更新；
- “保存”后 `config.yaml` 写入正确字段；
- “恢复默认”回到识别器类属性的值。

### 8.3 嵌入式端验证

```bash
uv run main
```

通过串口发送任务字（如 `M`），确认返回坐标与可视化图像格式正确。

---

## 9. 总结

- **识别器是 GC2026 的核心扩展点**：新视觉任务 = 新 `Detect` 子类。
- **契约优先**：先写 `TUNABLE_PARAMS` 和 `detect/draw_overlay/format_detection_info`，再考虑具体算法。
- **默认值唯一来源**：识别器源码类属性。
- **UI 自动渲染**：只要遵守契约，桌面端无需为新识别器写任何硬编码界面。
