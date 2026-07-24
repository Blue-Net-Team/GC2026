#!/bin/bash

# 如果有sd卡并且插上，设置自动挂载
# uid和gid可以用id -u和id -g查看
sudo mkdir -p /media/sdcard
echo "/dev/mmcblk1p1 /media/sdcard auto defaults,uid=1000,gid=1000 0 0" | sudo tee -a /etc/fstab
sudo mount -a

# 连接wifi
sudo nmcli dev wifi connect "EIC-FF" password "lckfb666"

# 解锁包的禁止更新
sudo apt-mark unhold accountsservice apparmor base-files bind9-host bind9-libs bluez bluez-cups bluez-obexd bsdutils bubblewrap ca-certificates cpp-9 cups cups-browsed cups-bsd cups-client cups-common cups-core-drivers cups-daemon cups-filters cups-filters-core-drivers cups-ipp-utils cups-ppdc cups-server-common distro-info-data dns-root-data dnsmasq-base e2fsprogs fdisk ffmpeg fonts-opensymbol gcc-9-base ghostscript ghostscript-x gir1.2-accountsservice-1.0 gir1.2-gdkpixbuf-2.0 gir1.2-gtk-3.0 gir1.2-nm-1.0 gir1.2-soup-2.4 gir1.2-vte-2.91 gnome-control-center gnome-control-center-data gnome-control-center-faces gnome-shell gnome-shell-common gstreamer1.0-alsa gstreamer1.0-gl gstreamer1.0-plugins-bad gstreamer1.0-plugins-base gstreamer1.0-plugins-base-apps gstreamer1.0-plugins-good gstreamer1.0-pulseaudio gstreamer1.0-tools gstreamer1.0-x gtk-update-icon-cache gtk2-engines-pixbuf hplip hplip-data krb5-locales libaccountsservice0 libapparmor1 libarchive13 libavcodec-dev libavcodec58 libavdevice-dev libavdevice58 libavfilter-dev libavfilter7 libavformat-dev libavformat58 libavresample-dev libavresample4 libavutil-dev libavutil56 libblkid1 libbluetooth3 libc-bin libc6 libcdio18 libcom-err2 libcups2 libcupsfilters1 libcupsimage2 libcurl3-gnutls libde265-0 libdvbv5-0 libexpat1 libext2fs2 libfdisk1 libfontembed1 libgail-common libgail18 libgd3 libgdk-pixbuf2.0-0 libgdk-pixbuf2.0-bin libgdk-pixbuf2.0-common libglib2.0-0 libglib2.0-bin libglib2.0-data libgnutls30 libgs9 libgs9-common libgssapi-krb5-2 libgstreamer-gl1.0-0 libgstreamer-plugins-bad1.0-0 libgstreamer-plugins-base1.0-0 libgstreamer-plugins-good1.0-0 libgstreamer1.0-0 libgtk-3-0 libgtk-3-bin libgtk-3-common libgtk2.0-0 libgtk2.0-bin libgtk2.0-common libharfbuzz-icu0 libharfbuzz0b libhpmud0 libk5crypto3 libkrb5-3 libkrb5support0 libldap-2.4-2 libldap-common libmount1 libmpg123-0 libmpv1 libmysqlclient21 libndp0 libnghttp2-14 libnm0 libnspr4 libnss-systemd libnss3 libopenjp2-7 liborc-0.4-0 libpam-modules libpam-modules-bin libpam-runtime libpam-s

# 更新软件
sudo apt-get update
# sudo apt-get upgrade

# 安装ssh
# 如果没有解锁包禁止更新，要在后面添加参数--allow-change-held-packages
sudo apt-get install openssh-client openssh-server -y
# 安装nano
sudo apt-get install nano -y
# 安装git
sudo apt-get install git -y
# 安装ifupdown，用于配置静态ip
sudo apt-get install ifupdown -y
# 安装i2c-tools
sudo apt-get install i2c-tools -y
# 安装中文字体 
sudo apt-get install fonts-wqy-microhei -y
# 安装v4l-utils
sudo apt-get install v4l-utils -y

# ------------------安装miniconda------------------
# 下载miniconda到Download文件夹
mkdir -p ~/Downloads
cd ~/Downloads
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-aarch64.sh
# 安装miniconda
bash Miniconda3-latest-Linux-aarch64.sh -b -p /media/sdcard/miniconda3
/media/sdcard/miniconda3/bin/conda init
source ~/.bashrc
conda config --set auto_activate_base false
# 修改全局pip源
pip config set global.index-url https://mirrors.aliyun.com/pypi/simple/

# ------------------ 配置github ssh ------------------
# 生成ssh key
ssh-keygen -t rsa -b 4096 -C "13377529851@qq.com" -f ~/.ssh/id_rsa -P ""
# 生成config文件
touch ~/.ssh/config
echo "Host github.com" >> ~/.ssh/config
echo "  HostName ssh.github.com" >> ~/.ssh/config
echo "  Port 22" >> ~/.ssh/config
echo "  User git" >> ~/.ssh/config

# ------------------ 配置静态ip ------------------
echo "auto eth0" | sudo tee -a /etc/network/interfaces
echo "iface eth0 inet static" | sudo tee -a /etc/network/interfaces
echo "address 169.254.133.100" | sudo tee -a /etc/network/interfaces
echo "netmask 255.255.0.0" | sudo tee -a /etc/network/interfaces

# 重启服务
sudo systemctl restart networking
# ------------------ 串口配置 ------------------
sudo usermod -a -G dialout $USER
sudo groupadd gpio
sudo usermod -a -G gpio $USER
sudo usermod -a -G i2c $USER