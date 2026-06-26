# GC2026 图传使用说明

> 本文档介绍 GC2026 项目中“远程图像传输”的工作原理、两种启动方式，以及收发两端的运行顺序。
> 
> 若你关心的是图传模块的代码实现，见 [`ImgTrans/ImgTrans.py`](../ImgTrans/ImgTrans.py)。

---

## 1. 图传的作用

GC2026 运行在嵌入式端（泰山派）上，摄像头采集到的画面需要实时回传到 PC 端，用于：

- **现场调试**：不连接显示器也能查看摄像头画面。
- **算法验证**：查看识别器处理后的结果（如颜色检测框、色环圆心）。
- **参数调参**：桌面调参应用（`app/`）需要实时预览来辅助调节识别器参数。

项目当前使用 **UDP + JPEG 分片** 的图传方案，源码集中在 `ImgTrans/` 目录。

---

## 2. 基本原理

### 2.1 传输协议：UDP + JPEG

- 服务端（发送端）把每一帧图像用 `cv2.imencode('.jpg', ...)` 编码成 JPEG 字节流。
- JPEG 数据被切分成多个 UDP 报文发送，接收端把分片按偏移量重组后解码显示。
- 采用 UDP 是为了低延迟；单帧数据量通过 JPEG 压缩和分片控制在以太网 MTU 范围内。

### 2.2 服务端与客户端

| 角色 | 运行位置 | 主要职责 |
|------|----------|----------|
| **服务端** | 嵌入式端（泰山派） | 监听 UDP 端口，等待客户端握手，随后向客户端发送图像帧 |
| **客户端** | Windows PC / 桌面调参应用 | 向服务端发送 `connect` 握手包，接收并重组图像帧 |

> 注意：代码里还保留了 `SendImgTCP` / `ReceiveImgTCP` 等 TCP 实现，但当前运行时（`main.py`、`app/`）统一使用 UDP。

### 2.3 连接握手

客户端首先需要向服务端发送一个内容为 `connect` 的 UDP 包：

```
客户端 ──UDP──> 服务端: b'connect'
服务端记录客户端 IP（B_IP），后续帧只发往该 IP
```

服务端在 `SendImgUDP.connecting()` 中等待这个握手包；收到后才会把图像数据发送出去。客户端掉线或切换网卡后，只需再次发送 `connect` 包即可恢复。

### 2.4 分片与重组

每个 UDP 报文的前 8 字节是帧头，采用网络字节序：

```
| total_length (4 bytes) | offset (4 bytes) | jpeg_chunk (<=1400 bytes) |
```

- `total_length`：当前帧 JPEG 数据总长度。
- `offset`：当前分片在 JPEG 数据中的偏移量。
- 单个分片最大 `1400` 字节，留有余量以适应不同网络的 MTU。

接收端（`ReceiveImgUDP`、`app/core/frame_source.py` 中的 `_UdpWorker`）维护一个 `bytearray` 缓冲区，按 `offset` 把分片写入对应位置。当已接收长度 `>= total_length` 时，把缓冲区交给 `cv2.imdecode()` 解码成 BGR 图像。

如果某帧在超时时间内没有收齐，接收端会丢弃当前缓冲区并尝试重连。

### 2.5 与 OpenCV `VideoCapture` 的多态接口

接收端类 `ReceiveImgUDP` 继承自 `cv2.VideoCapture`（接口定义见 `ImgTrans/IImgTrans.py`），并实现了统一的 `read()` 方法：

```python
res, img = cap.read()
```

返回值与 OpenCV 原生摄像头完全一致（`(bool, image)`）。这个设计的意义在于：

- **对上层代码透明**：无论是本地 `cv2.VideoCapture(0)` 还是远程 `ReceiveImgUDP(...)`，后续代码都按同样的方式调用 `cap.read()`。
- **方便复用**：`setup.py` 中的参数调试工具可以直接把图传接收器当作摄像头传入 `Setup(cap)`，无需为远程画面单独写一套逻辑。
- **可迭代**：`LoadWebCam` 进一步封装成迭代器，使得 `for img in cap:` 这种写法在图传接收端也能工作（见 `img_trans.py` 的 `main_windows()`）。

---

## 3. 两种图传方式

项目里有两条独立的图传链路，用途不同，不要混用。

### 3.1 方式 A：随主程序一起运行的图传（推荐）

这是嵌入式主程序 `main.py` 内置的图传协程 `img_trans()`，与图像处理、OLED 显示并行运行。

- 发送内容：
  - **`main` 模式**：识别结果的可视化图像（上侧为原图 + 检测标记，下侧为二值化图像）。
  - **`debug` 模式**：拨码开关切到 debug 后，直接发送原始摄像头画面。
- 默认端口：`8080`
- 绑定网卡：所有可用网卡（`SERVER_INTERFACE = ""`）
- 启动方式：在嵌入式端（泰山派）上执行 `uv run main`

### 3.2 方式 B：独立图传工具 `uv run img_trans`

这是独立的收发脚本，用于快速查看原始摄像头画面，不经过识别器处理。

它之所以能在 Linux 和 Windows 上使用**完全相同**的命令 `uv run img_trans`，是因为脚本内部通过 `sys.platform` 自动判断当前系统并分发到不同实现：

```python
async def main():
    if sys.platform == "linux":
        await main_linux()      # 作为发送端
    elif sys.platform == "win32":
        await main_windows()    # 作为接收端
```

- **Linux 端**：`main_linux()` 打开本地摄像头，以服务端身份发送原始画面。
- **Windows 端**：`main_windows()` 通过 `LoadWebCam` 接收画面，并用 OpenCV 窗口显示。

因此方式 B 的两端角色是：

| 操作系统 | 角色 | 实际执行函数 |
|----------|------|--------------|
| Linux / 嵌入式端（泰山派） | 发送端 | `main_linux()` |
| Windows | 接收端 | `main_windows()` |

参数说明：

- 发送内容：摄像头原始画面。
- 默认端口：`4444`
- 默认网卡：`eth0`

> `img_trans.py` 中 Windows 接收端的 IP 是**硬编码**的（`192.168.123.6`），使用前请根据实际嵌入式端 IP 修改。
> 
> 方法 B 的端口号 `4444` 同样写死在源码中，没有命令行参数可以修改；如需使用其他端口，必须同时修改 `img_trans.py` 中发送端 `SendImgUDP.create(...)` 与接收端 `LoadWebCam(...)` 的端口。

### 3.3 配合 `setup.py` 进行远程调参

图传最常见的用途之一，就是让 PC 端也能调试运行在嵌入式端（泰山派）上的摄像头画面。`setup.py` 提供了基于 OpenCV Trackbar 的命令行调参工具，支持把 `ReceiveImgUDP` 当作普通摄像头使用：

```bash
# 颜色阈值远程调参
uv run setup color --remote --capip <嵌入式端IP> --port <图传端口>

# 色环检测参数远程调参
uv run setup colorring --remote --capip <嵌入式端IP> --port <图传端口>
```

例如，配合 `uv run main` 内置的图传（端口 `8080`）：

```bash
uv run setup color --remote --capip 192.168.1.100 --port 8080
```

调参窗口打开后：

- 拖动 Trackbar 实时观察二值化效果；
- 按 `s` 将当前参数保存到 `config.yaml`；
- 按 `q` 退出。

如果没有远程图传需求，也可以直接调试本地摄像头：

```bash
uv run setup color --capid 0
uv run setup colorring --capid 0
```

---

## 4. 运行步骤

### 4.1 通用准备

1. 确保嵌入式端（泰山派）与 PC 端处于同一局域网，或者通过网线直连。
2. 获取嵌入式端 IP：
   - 查看 OLED 屏上的 `Server IP`；或
   - 在嵌入式端执行 `ifconfig`(推荐)。
3. 确认没有防火墙拦截对应端口（`8080` 或 `4444`）。

### 4.2 方式 A 运行流程（主程序图传）

1. **先启动服务端（嵌入式端）**：
   ```bash
   ssh lckfb@169.254.133.100 # 也可以使用其他方法进行ssh登录
   cd /userdata/code/GC2026
   uv run main
   ```
   等待日志输出：
   ```
   UDP 服务已启动 (监听所有网卡)
   ```

2. **再启动客户端（PC 端）**：

   **选项 1：桌面调参应用（推荐）**
   ```bash
   uv run --extra app app
   ```
   进入“图传接收”页面：
   - 选择“手动输入图传摄像头”。
   - 填入嵌入式端 IP，端口默认 `8080`。
   - 点击“连接”。

   **选项 2：独立 Windows 接收器**
   ```bash
   uv run img_trans
   ```
   但需要先把 `img_trans.py` 里 `main_windows()` 中的 IP 改为嵌入式端实际 IP。

3. 连接成功后，客户端即可看到实时画面；桌面应用还会显示 FPS 和帧数。

### 4.3 方式 B 运行流程（独立图传工具）

适用于只想看原始摄像头画面的场景。

1. **先启动发送端（Linux / 嵌入式端）**：
   ```bash
   uv run img_trans
   ```
   等待日志输出连接成功的信息。

2. **再启动接收端（Windows）**：
   ```bash
   uv run img_trans
   ```
   会弹出一个 OpenCV 窗口，按 `q` 退出。

> 如果收不到画面，先检查 `img_trans.py` 中 `main_windows()` 里的 `server_ip` 和 `self_ip` 是否与实际网络环境一致。

---

## 5. 关键代码与配置

### 5.1 `main.py` 中的图传常量

```python
SERVER_INTERFACE = ""    # 空字符串表示监听所有网卡
SERVER_PORT = 8080       # UDP 图传端口
```

- 修改端口只需改 `SERVER_PORT`；
- `SERVER_INTERFACE` 一般保持 `""`，否则绑定指定网卡可能导致某些网络环境下客户端无法连接。

### 5.2 `img_trans.py` 中的独立图传配置

```python
# Linux 发送端
stream = await SendImgUDP.create("eth0", 4444)

# Windows 接收端（硬编码示例）
cap = LoadWebCam("192.168.123.6", 4444, "192.168.123.2")
```

- `eth0` 可改成实际使用的网卡名（如 `wlan0`）。
- Windows 接收端需要根据嵌入式端 IP 修改第一个参数；第三个参数是本机 IP。
- **端口 `4444` 是硬编码的**，命令行不提供 `--port` 参数。若需要换成其他端口，必须同时修改发送端与接收端的源码。

### 5.3 桌面应用的默认端口

`app/core/frame_source.py` 与 `app/ui/screens/receiver_screen.py` 中默认端口都是 `8080`，与 `main.py` 保持一致。

---

## 6. 常见问题

### 6.1 客户端一直显示“连接中”，收不到画面

- 检查嵌入式端与 PC 是否在同一网段；
- 检查防火墙是否放行 `8080` / `4444` 端口；
- 确认先启动了服务端，再启动客户端；
- 查看服务端日志，确认收到了 `connect` 握手包。

### 6.2 画面卡顿或花屏

- 降低摄像头分辨率或 JPEG 质量；
- 检查网络抖动是否导致 UDP 分片丢失；
- 接收端超时后会丢弃不完整帧并显示 `read img timeout`，属于正常现象。

### 6.3 多客户端同时连接

当前实现只保留**最后一个**发送 `connect` 的客户端 IP。如果需要多人同时观看，需要在 `ImgTrans/ImgTrans.py` 中自行扩展客户端列表逻辑。

### 6.4 发送端切换网络后客户端没反应

服务端只向最后一次记录的客户端 IP 发送数据。如果客户端 IP 改变，重新点击“连接”或重启 Windows 接收端即可。

---

## 7. 小结

| 场景 | 启动命令 | 发送内容 | 默认端口 |
|------|----------|----------|----------|
| 主程序运行时图传 | 嵌入式端：`uv run main`<br>PC 端：`uv run --extra app app` | 识别结果可视化图 / debug 原图 | 8080 |
| 独立原始图传 | Linux：`uv run img_trans`<br>Windows：`uv run img_trans` | 摄像头原始画面 | 4444 |

只要记住“**先启服务端，再启客户端**”，并保证 IP 和端口一致，即可在 PC 端实时查看嵌入式端（泰山派）的摄像头画面。
