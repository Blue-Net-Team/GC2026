# GC-Setup App 产品需求文档（PRD）

> **项目**：gc-setup-qt  
> **用途**：工创赛（GC2026）嵌入式视觉系统桌面端调参软件  
> **目标平台**：Windows / Linux（桌面端）  
> **UI 框架**：PyQt6（或 PySide6）  
> **版本**：v1.0  
> **日期**：2026-06-16

---

## 1. 项目背景与目标

### 1.1 背景

GC2026 嵌入式视觉系统部署在泰山派（LCKFB）开发板上，通过 UDP 发送实时 JPEG 视频流。当前调参依赖 PC 端运行 `python setup.py color` / `colorring`，需要外接显示器、键盘鼠标，现场部署与现场快速调整极为不便。

### 1.2 目标

开发一款跨平台桌面端 PyQt 调参软件，实现：

1. **实时接收图传画面**：通过 UDP 协议接收开发板发送的视频流并实时显示
2. **可视化参数调节**：替代 OpenCV Trackbar，在桌面端调节 HSV 阈值、色环检测参数
3. **实时日志查看**：通过 SSH 实时接收服务端日志，支持级别过滤、搜索、复制
4. **配置导入/导出**：支持 GC2026 的 `config.yaml` 格式，调参结果可直接用于服务端
5. **Windows / Linux 双端适配**：开发调试在 Windows，比赛现场可在 Linux 笔记本或工控机上运行

---

## 2. 图传协议分析

### 2.1 协议概述

GC2026 图传模块（`ImgTrans/ImgTrans.py`）当前主力方案为 **UDP 分片图传**（`SendImgUDP` / `ReceiveImgUDP`）。App 仅需实现 **UDP 接收客户端**。

### 2.2 UDP 协议细节

**参考源码：** `E:/code/code_python/GC2026/ImgTrans/ImgTrans.py`

#### 2.2.1 连接建立机制

GC2026 的 UDP 图传采用**客户端主动发起连接**的模式：

```
客户端 → 服务端: b'connect' (UDP 单播到服务端 IP:端口)
服务端: 
  1. 接收 b'connect' 包，记录客户端 IP 地址
  2. 后续所有图传数据向该 IP 地址发送
  3. 仅保留最新客户端（切换后旧客户端不再接收）
```

**关键代码逻辑（服务端）：**

```python
# SendImgUDP._sync_connecting() — 等待连接
data, addr = self.server_socket.recvfrom(self.BUFFER_SIZE)
if data == b'connect' and addr[0] != self.host:
    self.B_IP, _ = addr          # 记录客户端 IP
    self._ip_lst = {addr[0]}     # 仅保留最新客户端

# SendImgUDP._sync_send() — 发送时也会检查新连接
while True:
    data, addr = self.server_socket.recvfrom(self.BUFFER_SIZE)
    if data == b'connect' and addr[0] != self.host:
        self.B_IP, _ = addr
        self._ip_lst = {addr[0]}  # 客户端切换网卡后自动更新
```

**连接特性：**

- 客户端只需发送一次 `b'connect'`，无需心跳保活
- 服务端在每次发送前非阻塞检查是否有新的 `connect` 请求
- 如果客户端切换网络（IP 变化），重新发送 `b'connect'` 即可
- 服务端始终只向**最后一个**发送 connect 的客户端发送数据

#### 2.2.2 数据包格式

每包结构：

```
+--------+--------+--------+
| 总长度 | 偏移量 | 数据块 |
| 4 bytes| 4 bytes| N bytes|
|  !II   |  !II   |        |
+--------+--------+--------+
```

- **总长度**（`!II` 第 1 个 I）：该帧 JPEG 的完整字节数
- **偏移量**（`!II` 第 2 个 I）：该数据块在帧中的起始位置
- **数据块**：JPEG 数据片段，最大 1400 字节（适配以太网 MTU）

**关键代码（服务端发送）：**

```python
offset = 0
while offset < total_length:
    chunk = img_data[offset:offset + self.CHUNK_MAX_SIZE]
    packet = struct.pack('!II', total_length, offset) + chunk
    for ip in self.clients_ip:
        self.server_socket.sendto(packet, (ip, self.port))
    offset += len(chunk)
```

#### 2.2.3 帧重组逻辑（客户端）

**参考源码：** `ReceiveImgUDP.read()`

```python
while True:
    data, addr = self.client_socket.recvfrom(65536)
    if addr != (self.host, self.port):
        continue

    total_length, offset = struct.unpack('!II', data[:8])
    chunk_data = data[8:]

    if self._recv_buffer is None or self._recv_total != total_length:
        self._recv_buffer = bytearray(total_length)
        self._recv_total = total_length
        self._recv_received = 0

    end = min(offset + len(chunk_data), self._recv_total)
    self._recv_buffer[offset:end] = chunk_data[:end - offset]
    self._recv_received += (end - offset)

    if self._recv_received >= self._recv_total:
        break
```

**Python 客户端实现要点：**

1. 创建 `socket.socket(socket.AF_INET, socket.SOCK_DGRAM)`
2. 绑定本机任意可用端口
3. 发送 `b'connect'` 到目标 IP:端口
4. 循环 `recvfrom()` 接收分片数据
5. 按 `!II` 头部重组帧
6. 超时后重置状态，可选重发 connect

### 2.3 服务端配置

- **端口**：8080（可配置）
- **编码**：JPEG，质量 70（固定）
- **发送端**：开发板绑定所有网卡
- **客户端 IP 管理**：仅保留最新 connect 的客户端

---

## 3. 功能需求

### 3.1 功能模块总览

App 提供 **6 个工作模式**，通过左侧导航栏或顶部 Tab 切换：

```
┌──────────────────────────────────────────────────────────────────────────────────────┐
│                                   GC-Setup App                                         │
├──────────────┬──────────────┬──────────────┬──────────────┬──────────────┬──────────────┤
│   纯图传接收   │   颜色调参    │   色环调参    │   日志查看    │   配置管理      │   服务管理    │
│   (Receiver)  │   (Color)    │  (ColorRing) │   (Log)      │  (Config)     │  (Service)   │
├──────────────┼──────────────┼──────────────┼──────────────┼──────────────┼──────────────┤
│ • UDP 接收   │ • R/G/B 三色 │ • 霍夫圆检测 │ • 实时日志    │ • 导入 YAML   │ • 启动/停止  │
│ • 帧重组     │ • HSV 阈值   │ • 高斯模糊   │ • 级别过滤    │ • 导出 YAML   │ • 重启服务   │
│ • JPEG 解码  │ • 实时二值化  │ • 二值化阈值 │ • 关键字搜索  │ • 预设管理    │ • 查看状态   │
│ • FPS 统计   │   预览       │ • 形态学操作 │ • 日志着色    │ • 恢复默认    │ • 开机自启   │
│ • 全屏画面   │ • 单颜色调参  │ • 半径范围   │ • 清空/复制   │ • 设备管理    │              │
│              │   互不影响   │ • 实时检测   │ • 自动滚动    │ • SSH 配置    │              │
│              │              │   预览       │              │ • Config 部署 │              │
└──────────────┴──────────────┴──────────────┴──────────────┴──────────────┴──────────────┘
```

**核心流程：**

1. 用户在**配置管理**中添加/编辑远程设备（名称 + IP + 端口 + SSH 凭据 + 部署路径）
2. 在任意模式下选择设备并点击连接
3. App 发送 `b'connect'` 建立 UDP 会话，同时建立 SSH 连接
4. 服务端记录客户端 IP，后续向该 IP 发送图传数据
5. 切换设备时自动断开旧连接、发送新 connect

**模式切换方式：**

- **窗口宽度 < 1000px**：左侧可折叠的侧边栏导航，或顶部 Tab 栏
- **窗口宽度 ≥ 1000px**：左侧固定 Navigation 侧边栏
- **快捷切换**：
  - 图传画面区域右键菜单快速切换到调参模式
  - 调参页面顶部工具栏可一键切换到纯图传模式（隐藏所有 UI，全屏看图）
  - 从服务管理页可一键跳转到对应设备的图传接收模式
  - 日志模式可与图传预览同时工作（宽屏左侧看图右侧看日志）

### 3.2 纯图传接收模式 (Receiver)

#### 3.2.1 功能定位

- **用途**：比赛现场或调试时，仅接收并显示图传画面，不进行任何调参
- **特点**：界面最简洁，画面区域最大化，适合作为监控屏使用

#### 3.2.2 连接设置

- **设备选择器**：下拉选择已保存的远程设备（名称 + IP:端口）
- **快捷连接**：显示最近使用的 3 个设备
- **手动连接**：输入框输入 IP 地址和端口（临时连接，不保存）
- 按钮：连接 / 断开
- 状态显示：未连接 / 连接中 / 已连接 / 重连中

#### 3.2.3 画面显示

- 实时显示解码后的图像，占满整个内容区
- 等比缩放，完整显示，**不裁剪任何像素**
- 缩放策略：类似 `Qt.KeepAspectRatio`，图像按比例缩放直到宽度或高度与容器一致
- 帧率显示（FPS）悬浮在画面角落
- 双击画面切换全屏模式
- 右键画面弹出快捷菜单（切换到调参模式、截图、切换设备）

#### 3.2.4 全屏模式

- 隐藏所有 UI（标题栏、导航栏、按钮）
- 图传画面占满整个屏幕
- 单击屏幕显示/隐藏悬浮控制条（FPS、连接状态、模式切换按钮）
- 从全屏模式可一键切换到颜色调参或色环调参模式
- 按 `Esc` 退出全屏

#### 3.2.5 网络统计面板（可收起）

- 实时 FPS
- 丢包率 / 丢帧计数
- 错误帧计数
- 当前服务端 IP:端口
- 连接时长
- 当前连接设备名称

---

### 3.3 颜色调参模式 (Color)

**对应 PC 端命令：`python setup.py color`**

GC2026 使用 HSV 颜色空间进行物料识别，每种颜色（R/G/B）需要配置以下参数：

| 参数 | 范围 | 说明 |
|------|------|------|
| `centre` | 0-179 | 色相中心值（OpenCV H 范围） |
| `error` | 0-30 | 色相容差（中心 ±error） |
| `L_S` | 0-255 | 饱和度下限 |
| `U_S` | 0-255 | 饱和度上限 |
| `L_V` | 0-255 | 明度下限 |
| `U_V` | 0-255 | 明度上限 |

#### 3.3.1 界面布局（窗口较窄 < 1000px）

```
┌─────────────────────┐
│  状态栏（IP/FPS）    │
├─────────────────────┤
│                     │
│   图传画面（上半）    │  ← 实时原图
│                     │
├─────────────────────┤
│ [R] [G] [B] 颜色Tab │
├─────────────────────┤
│                     │
│   二值化预览（下半）  │  ← 当前颜色的 mask
│                     │
├─────────────────────┤
│ centre: [====●====] │
│ error:  [==●======] │
│ L_S:    [●========] │
│ U_S:    [========●] │
│ L_V:    [●========] │
│ U_V:    [========●] │
├─────────────────────┤
│ [保存] [保存并部署]  │
└─────────────────────┘
```

#### 3.3.2 界面布局（窗口较宽 ≥ 1000px）

```
┌──────────────────────────────┬──────────────────────┐
│                              │                      │
│      实时原图（上半）          │                      │
│                              │   [R] [G] [B] 颜色Tab │
│   等比缩放，完整显示，无裁剪    │                      │
│   Qt.KeepAspectRatio 模式     │  centre: [====●====] │
│                              │  error:  [==●======] │
├──────────────────────────────┤  L_S:    [●========] │
│                              │  U_S:    [========●] │
│    二值化预览（下半）          │  L_V:    [●========] │
│                              │  U_V:    [========●] │
│  参考 GC2026 算法：            │                      │
│  1. GaussianBlur(5x5)        │  [保存] [保存并部署]  │
│  2. cvtColor(BGR→HSV)        │                      │
│  3. inRange(HSV阈值)          │                      │
│  4. medianBlur(3x3)          │                      │
│  5. morphologyEx(CLOSE)       │                      │
│                              │                      │
└──────────────────────────────┴──────────────────────┘
```

- **左侧 55%**：图像预览区，上下分布
  - 上：实时原图（来自 UDP 图传）
  - 下：二值化 mask 预览（使用当前 HSV 参数实时计算）
  - 两张图都使用 **Qt.KeepAspectRatio** 等比缩放，完整显示不裁剪
- **右侧 45%**：调参面板
  - R/G/B 颜色切换 Tab
  - 6 个参数滑动条 + 数值显示（QSlider + QSpinBox）
  - "保存" 和 "保存并部署" 按钮

#### 3.3.3 界面要求

- 顶部显示实时原图（来自图传）
- 中部显示当前选中颜色的二值化 mask 预览
- 底部 6 个滑动条（centre, error, L_S, U_S, L_V, U_V）
- 滑动条右侧显示当前数值
- 数值变化后 300ms debounce 再更新预览（防止卡顿）
- 提供"保存"按钮（保存到内存配置，不立即写文件）
- 提供"保存并部署"按钮（保存后通过 SSH 上传到远程设备）
- 提供"恢复默认"按钮

#### 3.3.4 调参逻辑

- R/G/B 三个颜色的参数**完全独立**，互不影响
- 切换颜色 Tab 时，滑动条自动切换到对应颜色的当前值
- 二值化预览实时反映当前选中颜色的 HSV 阈值效果
- 参考 PC 端 `TraditionalColorDetector.binarization()` 的算法逻辑：
  1. `GaussianBlur(img, (5, 5), 0)` — 高斯滤波降噪
  2. `cvtColor(img, COLOR_BGR2HSV)` — 转换到 HSV 色彩空间
  3. `inRange(hsv, low, up)` — 根据 HSV 阈值二值化
     - 红色跨越 0°/180° 边界时，使用两个 inRange + bitwise_or
  4. `medianBlur(mask, 3)` — 中值滤波去噪
  5. `morphologyEx(mask, MORPH_CLOSE, kernel)` — 闭运算连接断裂区域
- 预览图应显示检测到的物料外接矩形（绿色框）和中心点

---

### 3.4 色环调参模式 (ColorRing)

**对应 PC 端命令：`python setup.py colorring`**

色环检测使用霍夫圆变换，参数较多：

| 参数 | 类型 | 说明 |
|------|------|------|
| `gaussian_kernel_size` | 奇数 3-21 | 高斯模糊核大小 |
| `gaussian_sigma` | 0.5-5.0 | 高斯模糊标准差 |
| `threshold_value` | 0-255 | 二值化阈值 |
| `dilate_kernel_size` | 3-15 | 膨胀核大小 |
| `erode_iter` | 0-10 | 腐蚀迭代次数 |
| `hough_dp` | 0.5-2.0 | 霍夫变换累加器分辨率 |
| `hough_min_dist` | 10-200 | 圆心最小距离 |
| `hough_param1` | 10-200 | Canny 边缘检测阈值 |
| `hough_param2` | 10-200 | 累加器阈值 |
| `min_radius` | 10-300 | 最小圆半径 |
| `max_radius` | 50-500 | 最大圆半径 |
| `clahe_clip_limit` | 0.5-5.0 | CLAHE 对比度限制 |
| `clahe_tile_size` | 2-16 | CLAHE 网格大小 |
| `morph_kernel_size` | 3-15 | 形态学操作核大小 |
| `alpha` | 1.0-10.0 | 图像增强系数 |
| `expected_circles` | 1-10 | 期望检测到的圆数量 |

#### 3.4.1 界面布局（窗口较窄 < 1000px）

```
┌─────────────────────┐
│  状态栏（IP/FPS）    │
├─────────────────────┤
│                     │
│   图传画面（上半）    │  ← 实时原图
│                     │
├─────────────────────┤
│                     │
│   检测预览（下半）    │  ← 霍夫圆检测结果 + 中间处理图
│                     │
├─────────────────────┤
│ [预处理] [霍夫检测]   │
│ [后处理] 参数分组Tab  │
├─────────────────────┤
│ param1: [====●====] │
│ param2: [==●======] │
│ ...                 │
├─────────────────────┤
│ [保存] [保存并部署]  │
└─────────────────────┘
```

#### 3.4.2 界面布局（窗口较宽 ≥ 1000px）

```
┌──────────────────────────────┬──────────────────────┐
│                              │                      │
│      实时原图（上半）          │   [预处理][霍夫检测]  │
│                              │   [后处理] 参数分组   │
│   等比缩放，完整显示，无裁剪    │                      │
│   Qt.KeepAspectRatio 模式     │  param1: [====●====] │
│                              │  param2: [==●======] │
├──────────────────────────────┤  ...                 │
│                              │                      │
│    检测预览（下半）            │  [保存] [保存并部署]  │
│                              │                      │
│  参考 GC2026 算法：            │                      │
│  1. erode → dilate           │                      │
│  2. cvtColor(BGR→GRAY)       │                      │
│  3. CLAHE 对比度增强          │                      │
│  4. morphologyEx(GRADIENT)   │                      │
│  5. GaussianBlur × 3         │                      │
│  6. convertScaleAbs(α)       │                      │
│  7. threshold(二值化)         │                      │
│  8. HoughCircles(霍夫圆检测)  │                      │
│  9. 绘制检测到的圆             │                      │
│                              │                      │
└──────────────────────────────┴──────────────────────┘
```

- **左侧 55%**：图像预览区，上下分布
  - 上：实时原图（来自 UDP 图传）
  - 下：色环检测预览（显示检测到的圆和中间处理图）
  - 两张图都使用 **Qt.KeepAspectRatio** 等比缩放，完整显示不裁剪
- **右侧 45%**：调参面板
  - 参数分组 Tab（预处理 / 霍夫检测 / 后处理）
  - 滑动条 + 数值显示
  - "保存" 和 "保存并部署" 按钮

#### 3.4.3 界面要求

- 顶部显示实时原图
- 中部显示霍夫圆检测预览（绘制检测到的圆和中间处理过程）
- 参数按分组显示（预处理 / 霍夫检测 / 后处理）
- 滑动条 + 数值显示
- 提供"保存"和"保存并部署"按钮
- 提供"恢复默认"按钮

#### 3.4.4 调参逻辑

- 参数变化后实时更新检测预览
- 预览应显示检测到的圆（圆心 + 半径，红色圆环 + 蓝色圆心）
- 参考 PC 端 `ColorRingDetector.detect()` 的算法逻辑：
  1. `erode(img, None, iterations)` — 腐蚀
  2. `dilate(eroded, kernel, iterations=1)` — 膨胀
  3. `cvtColor(dilated, COLOR_BGR2GRAY)` — 转灰度
  4. `createCLAHE(clipLimit, tileGridSize).apply(gray)` — CLAHE 对比度增强
  5. `morphologyEx(gray, MORPH_GRADIENT, kernel)` — 形态学梯度
  6. `GaussianBlur(gradient, (k, k), sigma)` — 第一次高斯模糊
  7. `convertScaleAbs(blurred, alpha=alpha, beta=0)` — 对比度增强
  8. `GaussianBlur(scaled, (k, k), sigma)` — 第二次高斯模糊
  9. `threshold(blurred2, threshold_value, 255, THRESH_BINARY)` — 二值化
  10. `GaussianBlur(binary, (k+2, k+2), sigma)` — 第三次高斯模糊
  11. `HoughCircles(blurred3, HOUGH_GRADIENT, dp, minDist, param1, param2, minRadius, maxRadius)` — 霍夫圆检测
  12. 在原图上绘制检测到的圆（红色圆环，蓝色圆心）
- 预览图上下拼接：上侧原图（带绘制结果），下侧最终二值化/模糊图

---

### 3.5 配置管理模块 (Config)

#### 3.5.1 远程设备列表管理

**设备数据模型：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | String (UUID) | 设备唯一标识 |
| `name` | String | 设备名称（如"泰山派主车"、"备用设备"） |
| `ip` | String | 服务端 IP 地址 |
| `port` | Int | 图传端口号（默认 8080） |
| `deployPath` | String | 远程部署路径（默认 `/userdata/code/GC2026`） |
| `sshPort` | Int | SSH 端口号（默认 22） |
| `sshAuthType` | Enum | SSH 认证方式：`password` / `key` |
| `sshUsername` | String | SSH 登录用户名 |
| `sshPassword` | String | SSH 登录密码（加密存储） |
| `sshPrivateKey` | String | SSH 私钥内容（加密存储，key 认证时使用） |
| `sshKeyPassphrase` | String | 私钥密码短语（加密存储，可选） |
| `createdAt` | Long | 创建时间戳 |
| `lastUsedAt` | Long | 最后使用时间戳 |

**字段说明：**

- **`deployPath`**：设备上 GC2026 项目的部署路径，用于 config 文件替换和服务管理
  - 默认值：`/userdata/code/GC2026`
  - 对应 `run-main-auto.service` 中的 `WorkingDirectory`
  - config 文件位于 `${deployPath}/config.yaml`

- **`sshPort`**：SSH 服务端口，默认 22

- **`sshAuthType`**：支持密码认证和密钥认证两种方式
  - `password`：使用用户名+密码登录
  - `key`：使用私钥文件登录（更安全，推荐）

- **凭据安全：**
  - 密码和私钥使用系统密钥环（Windows DPAPI / Linux keyring）加密后存储
  - 内存中仅保留解密后的临时凭据
  - 导出/分享设备配置时，凭据字段脱敏处理

**功能需求：**

1. **设备列表展示**
   - 列表显示所有已保存设备（名称 + IP:端口）
   - 按最后使用时间排序，常用设备置顶
   - 支持搜索/筛选
   - 设备项显示 SSH 连接状态指示器（未连接/已连接）

2. **添加/编辑设备**
   - **基本信息**：名称、IP、图传端口
   - **部署路径**：输入框（默认 `/userdata/code/GC2026`）
   - **SSH 配置**：
     - 端口（默认 22）
     - 认证方式选择（密码 / 密钥）
     - 用户名输入框
     - 密码输入框（密码认证时显示）
     - 私钥导入按钮（密钥认证时显示，支持从文件选择器导入 `.pem` / `.key` 文件）
     - 私钥密码短语输入框（可选）
   - SSH 连接测试按钮（验证凭据是否正确）
   - 保存按钮（所有字段校验通过后保存）

3. **删除设备**
   - 右键菜单删除或选中后删除
   - 删除前确认弹窗

4. **快速连接**
   - 设备项右侧显示"连接"按钮
   - 点击后直接跳转到图传接收模式并建立 UDP + SSH 连接
   - 更新该设备的 `lastUsedAt`

**存储方式：**

- 使用本地 JSON 文件或 SQLite 数据库存储
- 设备列表与 YAML 配置分开存储
- 凭据字段使用系统密钥环加密（`keyring` 库）

---

#### 3.5.2 远程 Config 文件管理

**功能定位：**

调参完成后，直接将修改后的 `config.yaml` 上传到远程设备，替换原有配置，无需手动复制文件。

**使用流程：**

1. 用户在颜色/色环调参模式完成参数调节
2. 点击"保存并部署"按钮（或进入配置管理页操作）
3. App 通过 SSH 连接到远程设备
4. 将当前配置序列化为 YAML 格式
5. 上传到 `${deployPath}/config.yaml`，替换原文件
6. 可选：上传后自动重启服务使配置生效

**功能需求：**

1. **上传替换 Config**
   - 入口1：调参页面"保存并部署"按钮
   - 入口2：配置管理页设备项的"部署配置"按钮
   - 上传前确认弹窗（显示目标路径和设备名）
   - 上传进度指示
   - 上传成功/失败提示
   - 上传后可选自动重启服务

2. **下载远程 Config**
   - 从远程设备下载当前 `config.yaml`
   - 解析并导入到 App 的调参界面
   - 用于恢复设备上的配置到 App

3. **Config 文件备份**
   - 上传前自动备份远程设备上的原 `config.yaml`
   - 备份命名：`config.yaml.bak.YYYYMMDD_HHMMSS`
   - 支持查看备份列表和恢复指定备份

**SSH 文件操作实现：**

```python
# 使用 paramiko 库
class SshFileManager:
    def upload_config(self, yaml_content: str, remote_path: str) -> bool: ...
    def download_config(self, remote_path: str) -> str: ...
    def backup_config(self, remote_path: str) -> str: ...  # 返回备份路径
    def execute_command(self, command: str) -> CommandOutput: ...

# 上传配置流程
def deploy_config(device: RemoteDevice, config: AppConfig) -> None:
    ssh = SshClient(device.ip, device.ssh_port, device.ssh_username, device.ssh_password)
    ssh.connect()
    try:
        # 1. 备份原配置
        backup_path = f"{device.deploy_path}/config.yaml.bak.{timestamp()}"
        ssh.execute_command(f"cp {device.deploy_path}/config.yaml {backup_path}")
        
        # 2. 上传新配置
        yaml_content = yaml.safe_dump(config.to_dict())
        ssh.upload_config(yaml_content, f"{device.deploy_path}/config.yaml")
        
        # 3. 验证上传成功
        ssh.execute_command(f"cat {device.deploy_path}/config.yaml | head -5")
    finally:
        ssh.disconnect()
```

---

#### 3.5.3 服务管理

**功能定位：**

通过 SSH 远程管理设备上的 `main` 服务，实现启动、停止、重启和状态查看。

**目标服务：**

- **服务名**：`run-main-auto.service`（或用户自定义）
- **服务文件位置**：`/etc/systemd/system/run-main-auto.service`
- **工作目录**：`${deployPath}`（即 `/userdata/code/GC2026`）
- **启动命令**：`uv run main`（通过 systemd 管理）

**GC2026 服务参考：**

```ini
[Unit]
Description=Run Main Auto Service
After=multi-user.target ttys3-permission.service gpio-setup.service
Requires=ttys3-permission.service gpio-setup.service

[Service]
Type=simple
ExecStart=/home/lckfb/.local/bin/uv run main
User=lckfb
WorkingDirectory=/userdata/code/GC2026
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

**功能需求：**

1. **服务状态查看**
   - 显示当前服务状态（运行中 / 已停止 / 启动失败）
   - 显示服务启动时间
   - 显示最近退出代码（如果失败）

2. **服务控制**
   - **启动服务**：`systemctl start run-main-auto.service`
   - **停止服务**：`systemctl stop run-main-auto.service`
   - **重启服务**：`systemctl restart run-main-auto.service`
   - **启用开机自启**：`systemctl enable run-main-auto.service`
   - **禁用开机自启**：`systemctl disable run-main-auto.service`
   - 每个操作需要确认弹窗（防止误操作）
   - 操作后显示结果反馈

3. **服务配置**
   - 可自定义服务名（默认 `run-main-auto.service`）
   - 存储在设备配置中

**SSH 服务管理实现：**

```python
class ServiceManager:
    def get_service_status(self, service_name: str) -> ServiceStatus: ...
    def start_service(self, service_name: str) -> bool: ...
    def stop_service(self, service_name: str) -> bool: ...
    def restart_service(self, service_name: str) -> bool: ...
    def is_service_enabled(self, service_name: str) -> bool: ...
    def enable_service(self, service_name: str) -> bool: ...
    def disable_service(self, service_name: str) -> bool: ...

@dataclass
class ServiceStatus:
    state: ServiceState      # active, inactive, failed, unknown
    is_enabled: bool         # 是否开机自启
    uptime: str | None       # 运行时长
    last_exit_code: int | None  # 上次退出代码
    pid: int | None          # 进程ID

class ServiceState(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    FAILED = "failed"
    UNKNOWN = "unknown"
```

---

#### 3.5.4 日志查看

**功能定位：**

通过 SSH 实时查看设备上服务的运行日志，用于调试和排查问题。

> **注意：** 完整的日志查看功能已迁移至独立的 **日志查看模式（3.6 节）**。服务管理模式提供快速跳转到日志查看模式的入口，以及日志清空等管理操作。

**本模式提供的功能：**

- 日志清空按钮（`journalctl --vacuum-time=1d`）
- 一键跳转到日志查看模式（3.6 节）
- 查看当前日志文件路径和占用空间

---

#### 3.5.5 配置结构说明

两个调参模式共用同一个 `config.yaml` 文件：

```yaml
color:           # ← 颜色调参模式保存到这里
  R:
    centre: 0
    error: 12
    L_S: 41
    U_S: 255
    L_V: 29
    U_V: 255
  G: { ... }
  B: { ... }
color_ring:      # ← 色环调参模式保存到这里
  gaussian_kernel_size: 9
  gaussian_sigma: 1.5
  ...
# 以下字段由配置管理模块维护，调参模式不修改
min_material_area: 5940
max_material_area: 300000
need2cut_height: 0
target_angle: 46
```

---

#### 3.5.6 导入配置

- 调用系统文件选择器
- 支持 `.yaml` / `.yml` 文件
- 解析后自动填充所有调参模式的当前值
- 格式错误时提示用户

---

#### 3.5.7 导出配置

- 将当前所有参数（color + color_ring）序列化为 YAML
- 保存到 `~/Downloads/gc-setup-config.yaml`（默认下载目录）
- 格式必须与 GC2026 的 `config.yaml` 完全兼容

---

#### 3.5.8 预设管理

- 支持保存多组预设（如"室内光线"、"室外光线"）
- 快速切换预设
- 预设存储在 App 私有目录

---

### 3.6 日志查看模式 (Log)

**功能定位：**

独立的日志查看模式，通过 SSH 实时接收设备上服务的运行日志，用于调试和排查问题。与"服务管理"模式下的日志功能不同，本模式专注于**只读日志查看**，提供更优质的日志浏览体验，不包含服务控制功能。

**日志来源（与图传预览联动）：**

- **SSH 通道**：通过已建立的 SSH 连接执行 `journalctl -f -u run-main-auto.service --no-pager`，实时获取日志流
- 日志来源与连接的远程设备绑定，图传断开时日志模式自动断开

**功能需求：**

1. **实时日志流**
   - 类似 `journalctl -f` 的实时跟随模式
   - 通过 SSH 通道持续接收日志输出
   - 支持暂停/继续接收
   - 显示时间戳和日志级别

2. **历史日志查看**
   - 查看最近 N 行日志（默认 100 行）
   - 支持指定时间范围（如"最近 1 小时"、"今天"）
   - 支持关键字搜索/过滤
   - 支持日志级别过滤（ERROR / WARN / INFO / DEBUG）

3. **日志操作**
   - 复制单条日志或复制全部日志（到系统剪贴板）
   - 分享日志（通过系统分享面板）
   - 清空日志缓冲区

4. **日志界面**
   - 终端风格显示（等宽字体、彩色级别标识）
   - ERROR -> 红色，WARN -> 黄色，INFO -> 白色/蓝色，DEBUG -> 灰色
   - 自动滚动到底部（用户上滑浏览时暂停滚动，下滑到底部恢复）
   - 支持 `Ctrl + +/-` 缩放字体大小
   - 日志条目数量限制（保留最近 1000 条，自动丢弃旧日志）

5. **布局适配**
   - **窗口较窄**：全屏日志列表，顶部工具栏（级别过滤 + 搜索框 + 操作按钮）
   - **窗口较宽**：左侧图传预览（50%），右侧日志查看（50%），可边看画面边看日志

**SSH 日志查看接口：**

```python
class LogViewer:
    def get_recent_logs(self, lines: int = 100, since: str | None = None) -> list[LogEntry]: ...
    def start_log_stream(self, on_log_entry: Callable[[LogEntry], None]) -> LogStreamSession: ...
    def stop_log_stream(self, session: LogStreamSession) -> None: ...
    def clear_logs(self) -> bool: ...

@dataclass
class LogEntry:
    timestamp: str
    level: LogLevel
    message: str
    raw_line: str

class LogLevel(Enum):
    ERROR = "ERROR"
    WARN = "WARN"
    INFO = "INFO"
    DEBUG = "DEBUG"
    UNKNOWN = "UNKNOWN"
```

**日志命令参考：**

```bash
# 查看最近 100 行
journalctl -u run-main-auto.service -n 100 --no-pager

# 查看最近 1 小时
journalctl -u run-main-auto.service --since "1 hour ago" --no-pager

# 实时跟随
journalctl -u run-main-auto.service -f --no-pager

# 只查看错误
journalctl -u run-main-auto.service -p err --no-pager
```

**与图传接收的联动：**

- 日志查看模式**依赖**已建立的 SSH 连接（不需要额外输入）
- 切换到日志 Tab 时自动拉取最近 100 行历史日志，然后进入实时跟随模式
- 图传断开连接时日志查看自动停止并清空
- 宽屏模式下：图传信号接收独立于日志模式运行，左侧画面右侧日志互不干扰

---

## 4. UI/UX 设计

### 4.1 设计工具

- **设计软件**：Pencil（MCP 已配置）
- **设计稿格式**：`.pen` 文件
- **设计稿路径**：`docs/app.pen`
- **要求**：按 Pencil 设计稿实现 UI，保持布局和配色一致

### 4.2 布局策略

#### 4.2.1 窗口较窄（< 1000px）

```
┌─────────────────────────────────────────────┐
│  [≡]  GC-Setup App          [连接] [断开]    │
├─────────────────────────────────────────────┤
│                                             │
│                  内容区域                    │
│               （根据模式变化）                │
│                                             │
├─────────────────────────────────────────────┤
│ [接收] [颜色] [色环] [日志] [配置] [服务]     │
└─────────────────────────────────────────────┘
```

- 顶部工具栏：汉堡菜单展开导航、当前模式标题、连接控制
- 底部 Tab 栏或左侧抽屉导航：6 个模式切换
- 内容区域根据当前模式变化

#### 4.2.2 窗口较宽（≥ 1000px）

```
┌──────────┬────────────────────────────────────────────────────┐
│          │                                                    │
│ [接收]   │              图传预览画面（等比缩放）               │
│ [颜色]   │              Qt.KeepAspectRatio                    │
│ [色环]   │              完整显示，不裁剪像素                    │
│ [日志]   │                                                    │
│ [配置]   │                                                    │
│ [服务]   ├────────────────────────────────────────────────────┤
│          │   状态面板（FPS/丢包/连接状态）                      │
├──────────┼────────────────────────────────────────────────────┤
│          │   功能面板（调参 / 配置 / 服务 / 日志）              │
│          │   （根据当前模式变化）                               │
└──────────┴────────────────────────────────────────────────────┘
```

- **左侧导航栏**：固定显示 6 个模式图标 + 文字
- **中间区域**：图传预览区（所有模式都显示）
  - 图传画面使用 **Qt.KeepAspectRatio** 等比缩放
  - 完整显示，不裁剪任何像素
  - 接收模式：图传占满中间区域
  - 颜色调参：上原图 + 下二值化 mask（上下各 50%）
  - 色环调参：上原图 + 下检测预览（上下各 50%）
  - 日志模式：中间图传画面 + 右侧日志列表（互不干扰）
  - 配置/服务模式：图传缩小到左上角，或隐藏（可切换）
- **右侧区域**：功能面板（根据模式变化）
  - **颜色调参**：R/G/B Tab + 6 个滑动条 + 保存按钮
  - **色环调参**：参数分组 Tab + 滑动条 + 保存按钮
  - **日志查看**：日志列表（终端风格）+ 过滤工具栏
  - **配置管理**：设备列表 + 导入/导出 + SSH 配置
  - **服务管理**：服务状态卡片 + 控制按钮 + 日志终端
- 图传区域支持：
  - 双击全屏（隐藏所有 UI）
  - 右键快捷菜单（快速切换模式、截图）

### 4.3 主题与配色

- 支持深色/浅色主题（跟随系统，可手动切换）
- 主色调待定（按 Pencil 设计稿）
- 滑动条、按钮等组件使用 Qt Material 或自定义 QSS 风格

---

## 5. 技术架构

### 5.1 技术栈

| 层级 | 技术 |
|------|------|
| 语言 | Python 3.12+ |
| UI 框架 | PyQt6（推荐）或 PySide6 |
| 视觉样式 | QSS / Qt Material / 自定义主题 |
| 网络 | Python `socket`（UDP）+ `paramiko`（SSH） |
| 图像处理 | OpenCV-Python（`cv2`） |
| YAML | PyYAML |
| 加密存储 | `keyring` 库（系统密钥环） |
| 配置持久化 | JSON 文件 + SQLite（可选） |
| 异步任务 | `QThread` / `PyQt6.QtCore.QThreadPool` |

### 5.2 包结构

```
gc_setup_qt/
├── main.py                      # 程序入口
├── app.py                       # QApplication 初始化
├── ui/
│   ├── main_window.py           # 主窗口
│   ├── theme.py                 # 主题/QSS 管理
│   ├── widgets/                 # 自定义 QWidget
│   │   ├── video_label.py       # 图传显示 QLabel
│   │   ├── param_slider.py      # 参数滑动条组件
│   │   ├── color_tab_bar.py     # R/G/B 颜色切换 Tab
│   │   ├── param_group_tab.py   # 参数分组 Tab
│   │   ├── status_panel.py      # 状态面板
│   │   ├── connection_bar.py    # 连接设置栏
│   │   ├── device_list.py       # 设备列表
│   │   ├── device_edit_dialog.py # 设备编辑弹窗
│   │   ├── service_control_card.py # 服务控制卡片
│   │   └── log_terminal.py      # 日志终端显示
│   └── screens/                 # 各模式页面
│       ├── receiver_screen.py
│       ├── color_tuner_screen.py
│       ├── color_ring_tuner_screen.py
│       ├── log_viewer_screen.py
│       ├── config_screen.py
│       └── service_manage_screen.py
├── core/
│   ├── udp_img_receiver.py      # UDP 接收核心
│   ├── frame_assembler.py       # 帧重组逻辑
│   ├── connection_manager.py    # 连接状态管理
│   └── ssh_client.py            # SSH 客户端封装
├── vision/
│   ├── config_loader.py         # 配置加载基类
│   ├── traditional_color_detector.py  # HSV 颜色检测
│   └── color_ring_detector.py   # 色环检测
├── models/
│   ├── color_config.py
│   ├── color_ring_config.py
│   ├── app_config.py
│   ├── remote_device.py
│   ├── connection_state.py
│   ├── service_status.py
│   └── log_entry.py
├── repositories/
│   ├── config_repository.py
│   ├── device_repository.py
│   └── credential_store.py
└── utils/
    ├── debounce_util.py
    └── yaml_serializer.py
```

### 5.3 关键类设计

#### 5.3.1 UdpImgReceiver

```python
class UdpImgReceiver(QObject):
    frame_received = pyqtSignal(np.ndarray)
    connection_state_changed = pyqtSignal(ConnectionState)
    stats_changed = pyqtSignal(ReceiverStats)

    def __init__(self, server_ip: str, port: int, self_ip: str = "0.0.0.0"): ...
    def connect(self) -> bool: ...
    def receive_loop(self) -> None: ...
    def release(self) -> None: ...
    def switch_device(self, new_ip: str, new_port: int) -> bool: ...
```

**连接流程：**

1. `connect()` 发送 `b'connect'` UDP 包到服务端
2. 服务端记录客户端 IP，后续向该 IP 发送图传数据
3. `receive_loop()` 循环接收分片，按 `!II` 头部重组 JPEG 帧
4. 超时后重置状态，可重发 connect
5. `switch_device()` 关闭旧 socket，创建新 socket 发送 connect

#### 5.3.2 SshClient

```python
class SshClient(QObject):
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self): ...
    def connect_with_password(self, host: str, port: int, username: str, password: str) -> bool: ...
    def connect_with_key(self, host: str, port: int, username: str, private_key: str, passphrase: str | None = None) -> bool: ...
    def disconnect(self) -> None: ...
    def execute_command(self, command: str) -> CommandOutput: ...
    def upload_file(self, content: str, remote_path: str) -> bool: ...
    def download_file(self, remote_path: str) -> str: ...
    def open_shell_channel(self) -> paramiko.Channel: ...

@dataclass
class CommandOutput:
    stdout: str
    stderr: str
    exit_code: int
```

#### 5.3.3 FrameAssembler

```python
class FrameAssembler:
    def __init__(self): ...
    def process_packet(self, packet: bytes) -> bytes | None: ...
    def is_timeout(self, timeout_ms: int = 1000) -> bool: ...
    def reset(self) -> None: ...
```

---

## 6. 非功能需求

### 6.1 性能

| 指标 | 目标 |
|------|------|
| 图传帧率 | ≥ 15 FPS（在 WiFi 环境下） |
| 画面延迟 | ≤ 200ms |
| 内存占用 | ≤ 200MB（正常运行时） |
| 启动时间 | ≤ 3 秒 |

### 6.2 兼容性

- **最低 Python 版本**：3.12
- **操作系统**：Windows 10+ / Linux（Ubuntu 22.04+ / 泰山派系统）
- **网络**：WiFi 局域网（UDP 单播）

### 6.3 稳定性

- UDP 丢包不崩溃，自动等待下一帧
- 网络断开后自动重连（3 秒超时）
- 窗口缩放不丢失连接和参数

---

## 7. 联调与测试计划

### 7.1 联调环境

- 服务端：GC2026 泰山派开发板（`main.py` 运行图传）
- 客户端：Windows / Linux 笔记本
- 网络：同一 WiFi 局域网

### 7.2 测试项

| 测试项 | 方法 |
|--------|------|
| UDP 连接建立 | 抓包验证 connect 包发送 |
| 帧重组正确性 | 对比接收帧与服务端发送帧的 MD5 |
| 帧率测试 | 持续运行 5 分钟，记录平均 FPS |
| 丢包恢复 | 手动断开 WiFi 3 秒后恢复，验证自动重连 |
| YAML 兼容性 | 导出配置导入 GC2026，验证服务端正常读取 |
| 窗口缩放 | 反复调整窗口大小，验证无崩溃、状态保持 |
| 设备切换 | 连接设备A后切换到设备B，验证旧连接断开、新连接建立 |
| 设备列表 CRUD | 添加/编辑/删除设备，验证持久化存储 |
| SSH 连接 | 使用密码/密钥连接设备，验证凭据正确性 |
| Config 上传 | 修改配置后上传到远程设备，验证服务端读取正常 |
| Config 备份 | 上传前自动备份，验证备份文件生成 |
| 服务控制 | 启动/停止/重启服务，验证 systemctl 命令执行 |
| 日志查看 | 查看历史日志和实时日志流，验证输出正确 |
| 凭据加密 | 验证密码/私钥加密存储，导出时脱敏 |
| 图像缩放 | 验证 Qt.KeepAspectRatio 等比缩放，无像素裁剪 |
| 全屏模式 | 双击进入/退出全屏，验证 UI 隐藏/显示 |
| 二值化预览 | 调节 HSV 参数，验证 mask 实时更新 |
| 色环检测预览 | 调节霍夫参数，验证圆检测实时更新 |

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| UDP 丢包导致画面卡顿 | 高 | 实现超时丢弃 + 帧率统计提示 |
| 高分辨率图传内存溢出 | 中 | 限制缓冲区大小，JPEG 解码后按需缩放 |
| 窗口尺寸变化导致布局错乱 | 中 | 使用 QSplitter + 自适应布局，分别设计宽窄两套布局 |
| YAML 格式不兼容 | 高 | 严格按 GC2026 格式导出，联调验证 |
| 滑动条频繁触发卡顿 | 低 | 300ms debounce |
| SSH 连接失败 | 高 | 提供详细的错误提示（网络/凭据/权限） |
| 凭据泄露 | 高 | 使用系统密钥环加密，内存中不长期保留 |
| 误操作停止服务 | 中 | 所有服务操作需要二次确认 |
| 日志流占用带宽 | 低 | 支持暂停/恢复，限制历史日志行数 |
| 图像缩放黑边过多 | 低 | Qt.KeepAspectRatio 保证完整显示，黑边可接受 |
| 二值化计算卡顿 | 中 | 在后台线程执行 OpenCV 操作，避免阻塞 UI |
| 全屏模式快捷键冲突 | 低 | 全屏模式下监听 `Esc` 退出，提供显式退出按钮 |

---

## 9. 里程碑

| 阶段 | 内容 | 时间 |
|------|------|------|
| M1 | 项目搭建 + UDP 接收 + 画面显示 | 第 1 周 |
| M2 | 参数调参界面 + 滑动条组件 | 第 2 周 |
| M3 | YAML 导入/导出 + 配置管理 | 第 3 周 |
| M4 | SSH 连接 + Config 上传/下载 + 服务管理 + 日志查看 | 第 4 周 |
| M5 | 设计稿对接 + 双端布局适配 | 第 5 周 |
| M6 | 联调测试 + 优化 | 第 6 周 |

---

## 10. 附录

### 10.1 相关文件

- GC2026 图传源码：`E:/code/code_python/GC2026/ImgTrans/ImgTrans.py`
- GC2026 配置示例：`E:/code/code_python/GC2026/config.yaml`
- GC2026 调参工具：`E:/code/code_python/GC2026/setup.py`
- GC2026 主程序：`E:/code/code_python/GC2026/main.py`
- GC2026 服务配置：`E:/code/code_python/GC2026/run_auto/run-main-auto.service`
- GC2026 其他服务：`E:/code/code_python/GC2026/run_auto/*.service`
- UI 设计稿：`docs/app.pen`

### 10.2 参考协议

- UDP 分片头部格式：`struct.pack('!II', total_length, offset)`
- JPEG 帧结束标志：无显式 EOF，靠总长度判断
- 连接心跳：`b'connect'`

### 10.3 SSH 命令参考

```bash
# 服务管理
systemctl start run-main-auto.service
systemctl stop run-main-auto.service
systemctl restart run-main-auto.service
systemctl status run-main-auto.service --no-pager
systemctl enable run-main-auto.service
systemctl disable run-main-auto.service

# 日志查看
journalctl -u run-main-auto.service -n 100 --no-pager
journalctl -u run-main-auto.service -f --no-pager
journalctl -u run-main-auto.service --since "1 hour ago" --no-pager
journalctl -u run-main-auto.service -p err --no-pager

# 文件操作
cp config.yaml config.yaml.bak.20250612_143022
cat config.yaml | head -20
```

---

*本文档作为 gc-setup-qt 项目的初始 PRD，后续根据 Pencil 设计稿细化 UI 细节。*
