# GC2026 设计模式与约定背后的「为什么」

> 本文档回答阅读代码时最常冒出的问题：**这段代码为什么这么写？**
>
> [`DEVELOPMENT.md`](./DEVELOPMENT.md) 讲「怎么改」，本文档讲「为什么这样设计」。建议新人在动手改代码前先通读一遍——很多看似绕弯的写法，都是为了解决一个具体的坑。

---

## 1. 为什么分三层（main 层 / 应用层 / 基础设施层）

**问题**：全部写在一个 `main.py` 里不是更简单吗？

**答案**：这个项目的代码要在两种完全不同的环境运行——泰山派（无显示器、有 GPIO/串口）和 Windows PC（有显示器、无 GPIO）。同时还要被两类消费者调用——运行时（`main.py`）和调参工具（`app/`、`setup.py`）。

分层的本质是**按"变化的原因"切分代码**（这是单一职责原则在架构层面的应用，见第 2 节）：

| 层 | 变化的原因 | 不变的部分 |
|----|-----------|-----------|
| main 层 | 串口协议、协程编排、模式切换逻辑变了 | 不关心算法怎么实现 |
| 应用层 | 业务流程变了（先检测什么、结果怎么转换） | 不关心任务字从哪来、算法内部细节 |
| 基础设施层 | 算法换了、硬件平台换了 | 不关心业务 |

收益是具体的：

- 想换检测算法？只改 `detector/`，`main.py` 一行不动；
- 想加新任务字？只改 `task_table` 和 `applications.py`；
- 想在 Windows 上调试算法？识别器不依赖任何硬件，直接喂图片就能跑。

如果全部揉在一起，每次改算法都要冒着碰坏串口通信的风险。

---

## 2. 贯穿全项目的编程原则

后面各节会反复提到这些原则，这里先把它们和项目代码一一对应起来。**原则不是背出来的，是踩坑踩出来的**——每条原则在本项目里都对应一个真实的问题或事故。

### 2.1 SOLID 五原则

#### S — 单一职责原则（SRP）：一个模块只对一个"变化的原因"负责

- **宏观**：三层架构本身就是 SRP——`main.py` 只对"编排逻辑变化"负责，`applications.py` 只对"业务流程变化"负责，`detector/` 只对"算法变化"负责（见第 1 节）。
- **微观**：`Uart` 只管串口收发、`ConfigBridge` 只管 YAML ↔ 运行时对象的转换、`compute_file_hash()` 只管算 hash。
- **判断标准**：如果你给一个函数写注释时需要用到"**并且**"（"读取串口**并且**检测颜色"），它大概率违反了 SRP。
- **本项目红线**：`main.py` 里出现任何 HSV、霍夫圆等算法代码，就是 SRP 被破坏——算法细节属于识别器。

#### O — 开闭原则（OCP）：对扩展开放，对修改关闭

新增功能应该通过**增加新代码**完成，而不是**修改已有能跑的代码**。本项目有三处集中体现：

| 扩展点 | 新增时需要做的 | 不需要做的 |
|--------|---------------|-----------|
| 新任务字 | 在 `task_table` 加一行 | 修改 `main()` 协程的执行逻辑 |
| 新识别器 | 新建 `Detect` 子类 + 在 `DETECTOR_REGISTRY` 加一行 | 修改任何 UI 代码 |
| 新颜色 | 在 `color_groups` 追加一个字符串 | 修改 Tab 渲染、配置桥接、保存逻辑 |

反面就是 if-elif 链：每加一个分支都要打开主循环函数体改一遍，每次都冒着碰坏已有分支的风险。详见第 3、4 节。

#### L — 里氏替换原则（LSP）：子类必须能无缝替换父类

- `ReceiveImgUDP` 继承 `cv2.VideoCapture`：任何接受摄像头的代码（`Setup(cap)`、`LoadWebCam`），把图传接收端塞进去都能正常工作，不需要知道画面来自网络（见第 8 节）。
- `NoOpLED` / `NoOpSwitch` / `NoOpOLED` 与真实硬件类接口完全一致，`board_show()` 不关心自己手里拿的是真硬件还是占位对象（见第 7 节）。
- **本项目红线**：子类不能"收窄"父类的行为——比如某个识别器的 `detect()` 如果要求输入图像必须先旋转过，调用方（按 `Detect` 契约传原始帧）就会出错。契约写明的输入输出，子类必须遵守。

#### I — 接口隔离原则（ISP）：不强迫使用者依赖它不需要的接口

识别器的契约拆成了三组小接口，各取所需：

- **调参接口**：`TUNABLE_PARAMS` / `get_tunable_value` / `set_tunable_value` —— 只有 app 用；
- **预览/运行时接口**：`detect()` / `draw_overlay()` / `format_detection_info()` / `visualize()` —— `applications.py` 和 app 都用；
- **持久化接口**：`load_config()` / `save_config()` —— 运行时初始化与热加载用。

`main.py` 运行时从不接触调参接口，app 也从不直接调用 `tuple2str()` 这种运行时格式化方法。**每个消费者只看到与自己有关的那部分接口**，改其中一组接口时不影响其他消费者。

#### D — 依赖倒置原则（DIP）：上层依赖抽象，不依赖具体实现

- `applications.py` 通过 `Detect` 基类定义的接口（`detect()` / `visualize()`）调用识别器，不直接使用 `TraditionalColorDetector` 的私有方法——换一个识别器实现，应用层代码不变；
- `main.py` 通过 `task_table` 中登记的**方法签名约定**调用应用层，不知道 `detect_material` 内部是 HSV 还是深度学习；
- `core/config_bridge.py` 让识别器和 UI 都依赖 `AppConfig` dataclass 这个抽象，而不是 YAML 文件格式这个细节。

**判断标准**：`import` 的方向。上层（main）import 下层抽象（接口/基类）是正常的；如果基础设施层 import 了应用层或 UI，就是依赖方向反了。

### 2.2 其他贯穿项目的原则

#### DRY（Don't Repeat Yourself）：每一份知识只在一个地方表达

- **默认值唯一来源**：识别器类属性是默认值的唯一出处，`ConfigBridge` 的 `DEFAULT_COLOR_PARAMS` 是**运行时推导**出来的，不是手抄的第二份（见第 9 节）。如果默认值有两份，"恢复默认"按钮恢复的值和首次运行的值迟早不一样；
- `R`/`G`/`B` 三个任务字复用同一个 `detect_material` 方法，差异只有表里的附加参数；
- **反面警惕**：复制一段代码改两行，是 bug 的双倍产地——改一处忘另一处。

#### KISS（Keep It Simple）：选能满足需求的最简方案

- 配置热加载用**每秒算一次 SHA-256**，而不是引入 `watchdog` 库（见第 11 节）；
- 串口协议用**定长 8 位数字串**，而不是 JSON（见第 12 节）；
- 判断标准：当一个方案需要引入新依赖、新的失败模式，而收益只是"更标准/更高级"时，选简单的那个。

#### 显式优于隐式（Explicit is better than implicit）

- `task_table`、`DETECTOR_REGISTRY` 都是**显式注册表**，不用反射/装饰器自动扫描。隐式发现的问题是排查时无从下手——"为什么我的页面没出现？"在自动扫描机制下要理解扫描规则才能回答，在显式注册表下只需看一眼表里有没有那行；
- 这也是 Python 之禅（`import this`）的一条，本项目把它作为一贯取向。

#### Fail-fast 与优雅降级要分场合

- **关键硬件 fail-fast**：摄像头打不开，程序直接抛 `InitializationError` 退出——没有摄像头继续跑没有任何意义，带病运行只会让问题在更晚、更难查的时刻暴露；
- **非关键硬件优雅降级**：GPIO/OLED 初始化失败换成 NoOp 占位继续跑（见第 7 节）——没有 OLED 程序依然能完成视觉任务。
- 判断标准：**少了它，程序的核心价值还在不在**。在 → 降级；不在 → 立刻死，死得越早越好查。

#### 依赖取交集 / 向最弱的一端妥协

- **共享模块的依赖必须是所有消费者的交集**：`core/config_bridge.py` 和 `detector/` 被泰山派运行时（无 PyQt6）和桌面 app（有 PyQt6）共同使用，所以它们只能依赖 `cv2`/`numpy`/`loguru` 这类两边都有的库（见第 9 节）；
- **通信协议按对端能力最弱的设备设计**：串口协议定长、纯数字，因为接收方是 STM32 单片机而不是另一个 Python 进程（见第 12 节）。

---

## 3. `task_table`：为什么是字典映射而不是 if-elif

**问题**：`main.py` 里判断任务字，写 `if task_sign == "R": ... elif ...` 不是更直观吗？

**答案**：`task_table` 是**注册表模式（Registry）+ 策略模式（Strategy）**的组合：

```python
task_table = {
    "R": (applications.detect_material, "R"),
    "G": (applications.detect_material, "G"),
    "B": (applications.detect_material, "B"),
    "C": (applications.detect_circle, None),
    "F": (refresh_img, None),
}
```

- **开闭原则**：新增任务字 = 在表里加一行，不需要改动 `main()` 协程的执行逻辑。if-elif 链每加一个分支都要修改主循环函数体，容易引入回归。
- **关注点分离（SRP）**：`main()` 只负责"查表 → 调用"，"哪个任务字调用谁"这个决策被集中到了一张一眼能看全的表里。这也是约定「任务字映射**只能**放在 `task_table`，应用层不能自行决定响应哪些任务字」的原因——如果应用层也能决定，映射关系就散落在两处，查问题时要两边翻。
- **附加参数随表携带（DRY）**：`"R"` 和 `"G"` 复用同一个方法 `detect_material`，只是第二个参数不同。字典的值设计成二元组 `(方法, 附加参数)`，调用处统一为 `await task_table[t][0](img, task_table[t][1])`，一份调用代码适配所有任务。

**代价与约束**：被注册的方法必须遵守统一签名（协程、`(self, img, label=None)`、返回 `(coord, draw_img)`）。这就是 [`DEVELOPMENT.md`](./DEVELOPMENT.md) 里"应用层方法签名要求"存在的原因——**注册表模式的前提是所有的策略都有相同的接口**（这也是 LSP 的要求：表里的每个策略对调用方来说必须可互换）。

---

## 4. `DETECTOR_REGISTRY`：为什么桌面应用也要一张注册表

**问题**：app 里就两个调参页面，写两个 `if` 创建页面不就行了？

**答案**：[`app/ui/main_window.py`](../app/ui/main_window.py) 的 `DETECTOR_REGISTRY` 和 `task_table` 是同一个思路（注册表模式 + 开闭原则），解决的是**"新增识别器时 app 端要改多少地方"**的问题：

```python
DETECTOR_REGISTRY = [
    (TraditionalColorDetector, "颜色调参", "palette", "RGB.svg", True),
    (ColorRingDetector, "色环调参", "donut_large", "圆环.svg", False),
]
```

`MainWindow` 遍历这张表，为每个识别器自动创建 `DetectorTunerScreen`。新增识别器时只需加一行注册项——**UI 代码本身不需要任何修改**。

这也解释了为什么约定「新增识别器必须加入 `DETECTOR_REGISTRY` 才能在桌面端出现调参页面」：注册表是唯一的发现机制，app 不会用反射去扫描 `detector/` 目录（那样会做隐式魔法，排查问题时"为什么我的页面没出现"会非常难查）。**显式注册 > 隐式发现**，是这个项目的一贯取向（见 2.2 节）。

---

## 5. `TUNABLE_PARAMS`：为什么 UI 不写死，要靠 Schema 驱动

**问题**：调参页面直接写几个 `QSlider` 不是更快吗？

**答案**：识别器同时要服务两类消费者（运行时和调参工具）。如果 UI 写死：

- 每加一个参数要同时改识别器 + UI + 配置读写三处，任何一处漏改就是 bug（违反 DRY）；
- 参数的范围、步长、类型只有 UI 知道，识别器自己"不知道"自己有哪些可调参数。

`TUNABLE_PARAMS`（[`detector/schema.py`](../detector/schema.py)）让识别器**自描述**：声明自己有哪些参数、类型、范围、如何分组。然后：

- UI 根据 Schema **动态渲染**滑条和 Tab（`color-tabs` / `group-tabs` / `flat` 三种布局）——新增参数不用改 UI，符合开闭原则；
- `ConfigBridge` 根据 Schema **自动推导**默认配置——默认值保持单一来源；
- `set_tunable_value()` 根据 Schema 自动把 UI 传回的 `float` 截断为 `int`（OpenCV 的很多参数必须是整数，传 float 会直接抛 `Argument ... is required to be an integer`——这是真实踩过的坑）。

**一个推论**：颜色检测加新颜色（如黄色 Y）只需要在 `color_groups` 里追加一个字符串，Tab、默认配置、保存逻辑全部自动跟随——这就是 Schema 驱动的复利。

### 为什么 `section` 和 `group` 是两个字段

Schema 里有两种分组：`section`（颜色检测：每个颜色一组参数 + `global` 全局参数）和 `group`（色环检测：按预处理/霍夫检测/后处理分组）。它们对应的是**两种不同的参数结构**：

- 颜色检测的参数是**二维**的：`颜色 × 参数名`，同一个参数名（如 `centre`）在 R/G/B 下各有一份值 → 用 `section`；
- 色环检测的参数是**一维**的，只是按处理阶段归类展示 → 用 `group`。

混用会导致 UI 找不到参数（`color-tabs` 布局只按 `section` 查参数），所以约定「`section` 与 `group` 不要混用」。

---

## 6. `Detect` 基类：模板方法模式

**问题**：为什么不约定一个接口，非要搞个基类？

**答案**：[`detector/Detect.py`](../detector/Detect.py) 用的是**模板方法模式（Template Method）**：基类实现骨架，子类填钩子。

最典型的例子是 `visualize()`：运行时（`applications.py`）需要一张"上侧原图+标记、下侧二值图"的拼接图传给图传。这个拼接逻辑对所有识别器都一样，所以基类提供默认实现：

```python
def visualize(self, frame, result, binary):
    overlay = self.draw_overlay(frame, result, binary)   # 子类钩子
    binary_bgr = cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR) if binary.ndim == 2 else binary
    return np.vstack([overlay, binary_bgr])
```

子类只需实现三个钩子：`detect()` / `draw_overlay()` / `format_detection_info()`。特殊识别器可以整体覆盖 `visualize()`。

模板方法同时服务于两个原则：**DRY**（拼接逻辑只写一遍）和**依赖倒置**（`applications.py` 调用的是基类定义的 `visualize()`，不关心子类怎么实现钩子）。

另一个细节：`Detect` 继承 `ConfigLoader`，配置读写也是模板——`save_config()` 先读出原文件、只覆盖自己负责的段、再写回。**为什么不能直接全量覆盖写入**：`config.yaml` 是共享文件（system 段、颜色段、色环段、全局参数），一个识别器只管自己的段；全量覆盖会把别人维护的字段（以及文件里的注释）冲掉。

---

## 7. `NoOpLED` / `NoOpSwitch` / `NoOpOLED`：空对象模式

**问题**：Windows 上没有 GPIO，为什么不写 `if platform.system() == "Linux": led.on()`？

**答案**：[`utils/hardware_noop.py`](../utils/hardware_noop.py) 是**空对象模式（Null Object）**。`main.py` 初始化硬件时，GPIO/OLED 初始化失败就替换为 no-op 占位：

```python
try:
    switch = Switch(system.switch_pin, system.switch_reverse)
except Exception:
    switch = NoOpSwitch()   # 接口完全相同的"哑巴"对象
```

这样 `board_show()` 里可以放心地 `await switch.read_status()`、`await oled.display()`，**业务代码里没有任何平台判断分支**。

对比 `if linux: ...` 的写法：分支会散布在每一个用到硬件的地方，main 层代码会被平台判断淹没，而且新增一个硬件调用点时很容易漏写判断导致 Windows 上崩溃。空对象把"有没有这个硬件"的复杂度收敛到了初始化一处。这也是里氏替换原则的应用：`NoOpSwitch` 在任何接受 `Switch` 的地方都能无缝替换。

**什么时候不用它**：摄像头不能用空对象——没有摄像头程序就没有存在的意义，所以 `_initialize()` 里摄像头打开失败是直接抛 `InitializationError` 退出的。**非关键硬件降级、关键硬件 fail-fast**，这是有意区分（判断标准见 2.2 节）。

---

## 8. `ReceiveImgUDP` 继承 `cv2.VideoCapture`：适配器思路

**问题**：网络图传和摄像头明明是两个东西，为什么要继承？

**答案**：为了**对上层透明**（里氏替换原则）。`setup.py` 和 `img_trans.py` 的接收端都希望"拿到一个能 `cap.read()` 的东西"，至于画面来自本地 USB 摄像头还是 UDP 网络，上层不想关心。

让 `ReceiveImgUDP` 实现与 `cv2.VideoCapture` 相同的 `read() -> (bool, image)` 接口（通过继承），那么 `Setup(cap)`、`LoadWebCam` 这些代码可以无差别地接受两种来源——调参工具不用为"远程画面"单独写一套逻辑。这本质上是**面向接口编程**（依赖倒置）：上层依赖的是 `read()` 这个协议，不是具体设备。

> 代价提醒：这也让 `ReceiveImgUDP` 背上了 `VideoCapture` 的全部接口（多数用不到，与接口隔离原则有张力）。项目接受这个代价，因为换来的是上层零分支。

---

## 9. `ConfigBridge`：桥接模式，以及它为什么不能 import PyQt

**问题**：`config.yaml` 用 `yaml.safe_load` 读一下不就行了，为什么要专门的桥接层？

**答案**：[`core/config_bridge.py`](../core/config_bridge.py) 隔离了两个各自会变化的东西（桥接模式 + 依赖倒置）：

- **文件格式侧**：YAML 的结构、字段名、缺省处理；
- **运行时对象侧**：`AppConfig` / `SystemConfig` 这些带类型的 dataclass。

识别器和 UI 都只跟 dataclass 打交道，不碰 YAML。这样 YAML 结构调整（比如加字段、改默认值来源）时，只改桥接层。

文件顶部那段注释是**真实事故的预防**：

> 此模块被嵌入式主程序（main.py）和桌面调参应用（app）共同使用，请勿在此引入 app 专属的 GUI 依赖（如 PyQt6 / qasync）。

泰山派上只装了基础依赖（`uv sync`，没有 `--extra app`）。如果 `config_bridge.py` 引入了 PyQt6，`main.py` 在板子上会因 `ModuleNotFoundError` 直接起不来。**共享模块的依赖必须是所有消费者的交集**——这也是为什么 `detector/` 约定只依赖 `cv2`/`numpy`/`loguru`。

### 为什么默认值要从识别器推导，而不是 config_bridge 里再写一份

`DEFAULT_COLOR_PARAMS` 是调用 `_default_color_params()` 从 `TraditionalColorDetector.TUNABLE_PARAMS` 现场推导的，不是手写的常量（DRY）。如果桥接层手写一份默认值，那么"恢复默认"按钮恢复的值、首次运行的值、识别器源码里的值就会是三份——迟早漂移。**默认值只能有一个来源（single source of truth），就是识别器的类属性**，其他所有地方都从这里推导。

同理，仓库里 `config.yaml` 的值是**现场调好的当前值**，不是默认值——它只是恰好被提交进了仓库。

---

## 10. 为什么是 asyncio 协程，而不是多线程

**问题**：图像处理、OLED、图传、配置监视四件事，开四个线程不更直白？

**答案**：这四件事有一个共同特点——**绝大部分时间在等 I/O**（等串口字节、等 UDP 发送、等定时器），CPU 密集的只有检测算法本身。协程的优势（KISS：用更轻的机制解决 I/O 密集问题）：

- **共享状态不用抢**：`img_need_to_send`、`RUN_MODE` 这些全局状态在协程间传递，配合 `asyncio.Lock` 语义直白；多线程下每个共享变量都要考虑竞态；
- **单线程事件循环**意味着大部分时间不存在并发执行，只有显式 `await` 点才会切换——心智负担比线程小得多；
- 嵌入式板上资源有限，协程比线程轻。

### 代价：阻塞调用必须显式扔进线程池

协程模型的铁律是**事件循环不能被阻塞**。一旦某个协程里执行了同步阻塞调用（比如 `serial.read()` 死等字节），四个协程会全部卡死——OLED 不刷新、图传断流，现象非常诡异。

所以项目里有这些约定：

| 阻塞操作 | 处理 | 位置 |
|---------|------|------|
| 串口整包读取 | `_sync_read()` 放线程池，`new_read()` 用 `run_in_executor` 等待 | `utils/UART.py` |
| OLED I2C 写入 + PIL 绘制 | `run_in_executor` | `utils/gpio.py` |
| GPIO 初始化失败 | 降级为 NoOp，不阻塞启动 | `main.py` `_initialize()` |

**修改这些代码时的红线**：不要在协程里直接调用 `super().read()` / `display()` 的同步版本。CLAUDE.md 的「事件循环阻塞注意事项」一节就是为此存在。

### 为什么 `Applications` 里还有一把 `asyncio.Lock`

`config_watcher()` 热加载和 `main()` 检测是并发协程。如果检测跑到一半、配置恰好被重载，识别器参数会在一次检测中途被换掉，结果不可预测。所以 `detect_material()` / `detect_circle()` 和 `reload_config()` 共用一把锁，保证**参数加载和检测互斥**。这把锁不能省。

---

## 11. 配置热加载：为什么用 SHA-256 轮询

**问题**：为什么不用 `watchdog` 监听文件事件？

**答案**：[`config_watcher()`](../main.py) 每秒算一次 `config.yaml` 的 SHA-256，hash 变了才重载。理由（KISS + 零额外依赖）：

- **零额外依赖**：`watchdog` 是第三方库，嵌入式端要多装一个包；`hashlib` 是标准库；
- **语义正确**：文件事件会有一次保存触发多次（编辑器写临时文件再 rename）、事件丢失等边角问题；比 hash 只认"内容是否真的变了"，天然去抖；
- 1 秒轮询对调参场景足够快，代价是一次小文件读取，可以忽略。

热加载的范围是**检测器参数 + `udp_target_ip`**。`system` 段其他字段（串口、GPIO 引脚）不在热加载范围内——这些变了本来就需要重建硬件句柄，热更新没有意义，重启更可靠。

---

## 12. `tuple2str`：为什么是定长 8 位数字串，而不是 JSON

**问题**：回传 `{"x":12,"y":-115}` 不是更易读吗？

**答案**：通信对端是 **STM32 单片机**，不是另一个 Python 进程（协议向最弱的一端妥协）：

- 单片机解析 JSON 需要引入 cJSON 之类的库，而定长字符串只需要固定偏移的 `atoi`；
- 定长帧（`@XXXXXXXX#` 恒为 10 字节）让单片机可以用最简单的状态机收包，不需要处理变长；
- 串口带宽 115200 下，帧越短越好。

`FFFFFFFF` 作为"未识别到"的哨兵值也是为此设计：格式合法（8 位）、不可能与真实坐标混淆（`F` 不是数字位能出现的字符）、单片机一次字符串比较即可判断。

---

## 13. 为什么 `setup.py` 被 `app/` 取代

OpenCV Trackbar 方案的根本问题：

1. **参数多了没法用**：所有滑条堆在一个窗口，颜色多了以后完全没法维护；
2. **Trackbar 只能调整数**：步长、小数、奇数约束（卷积核）都表达不了；
3. **参数与 UI 强耦合**：每加一个参数要手写一行 `cv2.createTrackbar`（违反 DRY 和开闭原则），正是 Schema 驱动要解决的问题；
4. **没有图传接收/配置管理/服务管理能力**，这些在赛场是刚需（不用抱显示器去调车）。

`app/`（PyQt6 + Schema 驱动 UI）一次性解决了这四个问题，因此 `setup.py` 标记为废弃——但**保留兼容**，因为旧的调参脚本和文档引用它，且它的 Trackbar 代码也是理解 `color_threshold` 结构的最短路径。

---

## 14. 设计取向速查

读完上面各节，可以总结出这个项目的几条一贯取向（括号内是对应的原则），改代码时与之保持一致：

| 取向 | 体现 | 原则 |
|------|------|------|
| **显式注册 > 隐式发现** | `task_table`、`DETECTOR_REGISTRY` 都是显式表 | Explicit > Implicit |
| **默认值唯一来源** | 识别器类属性 → 其他地方全部推导 | DRY |
| **扩展靠加代码，不靠改代码** | 三张表 + Schema 驱动 UI | 开闭原则 |
| **上层依赖抽象接口** | 应用层调 `Detect` 基类接口，UI 依赖 `AppConfig` | 依赖倒置 |
| **子类随处可替换** | `NoOp*` 占位、图传接收端冒充摄像头 | 里氏替换 |
| **共享模块依赖取交集** | `core/`、`detector/` 不引入 PyQt6 | 接口隔离 + 依赖取交集 |
| **非关键硬件降级，关键硬件 fail-fast** | NoOp 占位 vs 摄像头失败直接退出 | Fail-fast 分场合 |
| **协议向最弱的一端妥协** | 串口协议按 STM32 的能力设计（定长、纯数字） | KISS |
| **能不加依赖就不加** | SHA-256 轮询代替 watchdog | KISS |

---

## 15. 延伸阅读

- [`DEVELOPMENT.md`](./DEVELOPMENT.md) — 识别器开发契约、新增功能的标准流程（"怎么做"）
- [`IMG_TRANS.md`](./IMG_TRANS.md) — UDP 分片图传的协议细节
- [`DEPLOYMENT.md`](./DEPLOYMENT.md) — 泰山派部署全流程
