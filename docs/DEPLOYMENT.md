# GC2026 泰山派（LCKFB）部署手册

> 本文档面向首次接触本项目的开发者，目标是在一台全新的泰山派开发板上从零完成 GC2026 视觉程序的部署，并能开机自启运行。
>
> 本项目使用 Claude Code / opencode 等 coding agent 工具开发。文中标注「可让 coding agent 操作」的步骤，直接把现象描述给 agent 工具并让它登录泰山派处理即可。

---

## 1. 硬件与登录方式

| 项目 | 值 |
|------|-----|
| 开发板 | 泰山派（LCKFB），aarch64 |
| 部署用户 | `lckfb` |
| 部署路径 | `/userdata/code/GC2026` |
| 有线静态 IP | `169.254.133.100`（eth0） |
| 串口 | `/dev/ttyS3`，波特率 115200 8N1 |

### 1.1 SSH 登录（推荐）

```bash
ssh -o StrictHostKeyChecking=no -i "C:/Users/IVEN/.ssh/tspi" lckfb@169.254.133.100
```

`~/.ssh/config` 参考配置：

```
Host 泰山派-wire
  HostName 169.254.133.100
  User lckfb
  IdentityFile "C:\\Users\\IVEN\\.ssh\\tspi"
```

### 1.2 无法联网时的登录方式

如果板子还没配好网络（首次上电、WiFi 连不上、静态 IP 配错），可以：

- **USB adb**：用 Type-C 数据线连接电脑与泰山派的 OTG 口，然后：
  ```bash
  adb devices     # 确认识别到设备（应列出一行 device）
  adb shell       # 直接进入泰山派的 shell
  ```
- **串口终端**：通过 USB 转串口模块接泰山派调试串口，用串口工具登录。

把上述登录方式告知 coding agent 工具，让 agent 进入泰山派后执行后续网络配置。

---

## 2. 新板初始化（environments.sh）

项目根目录的 `environments.sh` 是一次性的初始化脚本，完成：SD 卡挂载、WiFi 连接、apt 包解锁、基础软件安装、静态 IP 配置、串口/GPIO 用户组配置。

```bash
cd /userdata/code/GC2026
sudo bash environments.sh
```

> 注意：脚本中的 WiFi 名称/密码（`EIC-FF` / `lckfb666`）、GitHub 邮箱、静态 IP 都是示例值，使用前按实际情况修改。

### 2.1 apt 包被锁定（held packages）

泰山派官方镜像默认 `apt-mark hold` 了一批系统包，直接 `apt-get install` 会报 `you have held broken packages`。

**解决方法**：执行 `environments.sh` 第 13 行的超长 `sudo apt-mark unhold ...` 命令解锁全部包，然后再安装。这一步也可以直接让 coding agent 登录泰山派操作——把「包被锁定，需要解锁」告诉 agent 即可。

解锁后如果个别包仍报 held，可在安装命令后追加 `--allow-change-held-packages`。

### 2.2 安装 uv

`environments.sh` 中安装 miniconda 的步骤对本项目并非必需——项目统一使用 `uv` 管理 Python 环境。在泰山派上安装 uv：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
source ~/.bashrc   # 或重新登录，确保 ~/.local/bin 在 PATH 中
uv --version
```

`run-main-auto.service` 中 `ExecStart` 写死了 `/home/lckfb/.local/bin/uv`，请确认 `which uv` 的输出与之一致。

---

## 3. WiFi 连接

### 3.1 前置条件

**必须安装 WiFi 天线**。不装天线时 `nmcli dev wifi list` 可能扫不到任何热点，或信号极差导致认证失败。

### 3.2 正常连接

```bash
sudo nmcli device wifi rescan
sudo nmcli device wifi list
sudo nmcli device wifi connect "<SSID>" password "<密码>"
```

项目中的 `utils/wifi_connect.py` 对上述命令做了封装，`environments.sh` 第 10 行也会尝试连接默认热点。

### 3.3 扫得到但连不上（常见坑）

即使 `nmcli dev wifi list` 能扫到热点，使用 `nmcli dev wifi connect` 输入**正确的密码**也可能连接失败（泰山派的 wpa_supplicant / 网卡固件问题）。

**此时不要反复重试**。正确做法：让 coding agent 工具通过 adb 或 ssh 登录进泰山派，在板子上直接操作排查：

```bash
# 查看连接失败的详细原因
sudo nmcli device wifi connect "<SSID>" password "<密码>"
sudo journalctl -u NetworkManager -n 50 --no-pager

# 常见处理：删除旧连接配置后重连
sudo nmcli connection delete "<SSID>"
sudo nmcli device wifi connect "<SSID>" password "<密码>"

# 或检查 wpa_supplicant 状态
sudo systemctl status wpa_supplicant
sudo systemctl restart wpa_supplicant NetworkManager
```

---

## 4. 目录权限（/userdata）

程序需要在 `/userdata/code/GC2026` 下读写（日志、配置、git 操作）。如果该目录属主不是 `lckfb`，`uv run main` 和 systemd 服务都会失败。

**解决方法**：把「/userdata/code/GC2026 目录下权限有误，需要让用户 lckfb 能在该目录下增删查改」告知 coding agent 工具，让它登录泰山派执行：

```bash
sudo mkdir -p /userdata/code
sudo chown -R lckfb:lckfb /userdata/code
# 验证：lckfb 用户可以正常创建/删除文件
su - lckfb -c 'touch /userdata/code/GC2026/.perm_test && rm /userdata/code/GC2026/.perm_test && echo OK'
```

---

## 5. 静态 IP 配置

`environments.sh` 会把 eth0 配置为静态 IP `169.254.133.100/16`（写入 `/etc/network/interfaces` 并重启 networking）。如需修改：

```bash
sudo nano /etc/network/interfaces
# 修改 address 行
sudo systemctl restart networking
ip addr show eth0   # 验证
```

> 若板子实际网卡名不是 `eth0`（用 `ip link` 确认），需同步修改 `interfaces` 文件中的网卡名。这一步可直接交给 coding agent 完成。

WiFi 需要固定 IP 时（图传更方便），建议用 NetworkManager 配置：

```bash
sudo nmcli connection modify "<SSID>" ipv4.method manual ipv4.addresses 192.168.1.100/24 ipv4.gateway 192.168.1.1
sudo nmcli connection up "<SSID>"
```

---

## 6. 串口 / GPIO / I2C 权限

视觉程序需要访问 `/dev/ttyS3`、`/dev/gpiochip0-4`、I2C 总线。配置分两层，可直接交给 coding agent 完成：

### 6.1 用户组（environments.sh 已包含）

```bash
sudo usermod -a -G dialout $USER
sudo groupadd -f gpio
sudo usermod -a -G gpio $USER
sudo usermod -a -G i2c $USER
# 重新登录后生效
```

### 6.2 开机权限服务（run_auto/ 下已提供）

`run_auto/` 目录提供了三个权限服务的组合方案：

| 服务 | 作用 |
|------|------|
| `ttys3-permission.service` | 开机将 `/dev/ttyS3` 改为 666 |
| `gpio-setup.service` | 执行 `run_before_use_GPIO.sh`，将 gpiochip0-4 属组改为 gpio、权限 660 |
| `run-auto-shell-permission.service` | 给 `run_auto/*.sh` 加执行权限 |

> 说明：`run_before_use_GPIO.sh` 要求 `lckfb` 已加入 `gpio` 组（见 6.1）。若希望重启后权限更稳定，也可以自行增加 udev 规则（如 `/etc/udev/rules.d/99-gc2026.rules` 中 `KERNEL=="ttyS3", MODE="0666"`），当前项目默认使用上述 systemd 服务方案。

---

## 7. 部署代码并验证

```bash
ssh lckfb@169.254.133.100
cd /userdata/code
git clone <仓库地址> GC2026   # 已有仓库则 git pull
cd GC2026
uv sync
uv run main
```

验证点：

1. 日志出现 `UDP 服务已启动 (监听所有网卡)`；
2. OLED 显示 `Main` 模式与 `Server IP`；
3. PC 端 `uv run app`（需先 `uv sync --extra app`）进入图传接收页，填板子 IP + 端口 8080 能看到画面。

摄像头打不开时，执行 `v4l2-ctl --list-devices` 查看实际摄像头名，并修改 `config.yaml` 的 `system.camera_name` 与之匹配。

### 7.1 分层验证（出问题时分层定位，不要直接连整车）

1. **先验证摄像头 + 图传**：不接 STM32，拨码开关切到 debug 模式（OLED 显示 `Debug`），PC 端能收到原始画面即说明摄像头、图传、网络三层都正常；
2. **再验证串口收发**：拨回 main 模式，用 USB 转串口模块（或另一台机器的串口工具，115200 8N1）向 `/dev/ttyS3` 发送 `@R#`，应收到形如 `@10120115#` 的应答（未识别到时为 `@FFFFFFFF#`）；也可用一段临时 Python 脚本通过 `serial.Serial('/dev/ttyS3', 115200)` 发帧测试；
3. **最后接 STM32 跑完整闭环**：电控端发送任务字，观察板端日志的 `收到任务` / `发送结果` 与 OLED 上的识别结果。

这样出问题能立刻定位是摄像头层、串口层还是电控配合层，而不是在整车联调时抓瞎。

---

## 8. 开机自启（systemd）

`run_auto/` 下的服务文件复制到系统目录并启用：

```bash
sudo cp /userdata/code/GC2026/run_auto/*.service /etc/systemd/system/
sudo systemctl daemon-reload

# 权限服务（run-main-auto 依赖它们）
sudo systemctl enable --now run-auto-shell-permission.service
sudo systemctl enable --now ttys3-permission.service
sudo systemctl enable --now gpio-setup.service

# 可选：每次开机清空 main 服务旧日志
sudo systemctl enable clear-run-main-logs.service

# 主程序
sudo systemctl enable --now run-main-auto.service
```

`run-main-auto.service` 的关键配置：

```ini
ExecStart=/home/lckfb/.local/bin/uv run main
User=lckfb
WorkingDirectory=/userdata/code/GC2026
```

启用后验证：

```bash
systemctl status run-main-auto.service --no-pager
journalctl -u run-main-auto.service -f --no-pager   # 实时日志
```

> 板载 RGB LED 闪烁服务 `board_led_setup.service` 为可选项（`change_board_led.sh` 是常驻循环脚本），不需要状态指示可不启用。

---

## 9. 常见问题速查

| 现象 | 排查 |
|------|------|
| `apt-get install` 报 held packages | 执行 `environments.sh` 的 `apt-mark unhold`（见 2.1），可让 coding agent 操作 |
| WiFi 扫不到热点 | 检查 WiFi 天线是否安装 |
| WiFi 密码正确但连不上 | 见 3.3，让 coding agent 登录板子处理 |
| `uv run main` 报权限错误（串口/GPIO） | 确认 6.1 用户组已配置并重新登录；确认 6.2 三个权限服务已启用 |
| systemd 服务启动失败 | `journalctl -u run-main-auto.service -n 50`；常见原因是 uv 路径不对或 `/userdata` 权限问题（见第 4 节） |
| 摄像头打不开 | `v4l2-ctl --list-devices` 确认名称，改 `config.yaml` 的 `system.camera_name` |
| PC 收不到图传 | 确认板子与 PC 同网段、防火墙放行 8080；板端日志是否出现「UDP 客户端已连接」 |

---

## 10. 相关文件索引

| 文件 | 说明 |
|------|------|
| `environments.sh` | 新板一次性初始化脚本 |
| `run_auto/run-main-auto.service` | 主程序开机自启服务 |
| `run_auto/ttys3-permission.service` | 串口权限服务 |
| `run_auto/gpio-setup.service` + `run_before_use_GPIO.sh` | GPIO 权限服务 |
| `run_auto/run-auto-shell-permission.service` | 脚本执行权限服务 |
| `run_auto/clear-run-main-logs.service` | 开机清理 main 服务日志（可选） |
| `run_auto/board_led_setup.service` + `change_board_led.sh` | 板载 LED 指示（可选） |
| `config.yaml` | 全部运行参数（串口/UDP/GPIO/检测阈值） |
