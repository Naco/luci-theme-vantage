# Vantage UniFi AP overlay

[中文说明](#中文说明)

This add-on for the stock Vantage dashboard displays local UniFi access points as compact cards to the right of LAN, including on phone-sized screens. Cards contain the controller's device name, model and management IPv4 address. The LAN grouping follows the router's LAN subnet. The cards do not report live availability, client counts or physical switch topology.

## Install

The preview targets OpenWrt 25.12 and the unmodified upstream `luci-app-vantage 1.0.16-r1` APK, in the dashboard's wired-router view. It requires Python 3 and an existing UniFi Network Application container on the same Docker host. The supported container layout has the legacy `mongo` client, database `ace` on container-local port 27117, and the `device` inventory accessible within that container. The installer verifies the dashboard file hashes and tries the controller read before writing. Builds from other feeds can have different hashes even when they use the same version number.

1. Download the add-on and `SHA256SUMS` from [Releases](https://github.com/Naco/luci-theme-vantage/releases), and check the archive with `sha256sum -c SHA256SUMS`.
2. Copy the archive to OpenWrt. As root, extract it in a directory you control and enter the extracted `addons/unifi-aps` directory.
3. Run `python3 -B install.py install --container unifi-network`, substituting the actual container name from `docker ps`.
4. Refresh the dashboard. A standard administrator session can read the AP list. For a custom LuCI login, grant only the separate `luci-unifi-aps` read ACL if that login should see the list.

The collector runs a fixed local Docker command and a projected, read-only inventory query when the dashboard needs it. It caches the result for 60 seconds. There is no credential prompt, controller configuration change or Docker restart. Other UniFi deployment layouts, routers displaying Vantage's local Wi-Fi radio branches, and other Vantage builds are outside the preview's support.

To remove the add-on, run `python3 -B install.py uninstall` from that directory. Original files are stored under `/etc/vantage-unifi-aps-backup`. Remove the overlay before updating Vantage. The uninstaller refuses to overwrite files changed by a subsequent package update.

## 中文说明

这是 Vantage 仪表盘的 UniFi AP 扩展预览版。LAN 右侧显示紧凑卡片，包含 AP 名称、型号和管理 IP。拓扑按 LAN 网段归组，卡片只展示控制器的设备清单。

适用于 OpenWrt 25.12、原版 `luci-app-vantage 1.0.16-r1` 和同一台 OpenWrt 上的 UniFi Docker 控制器。仪表盘需使用有线接口视图，控制器容器需符合上面所列的本地数据库布局。下载后先核对 SHA-256，解压，进入其中的 `addons/unifi-aps` 目录，以 root 运行 `python3 -B install.py install --container unifi-network`，把容器名换成自己的。卸载用 `python3 -B install.py uninstall`。升级 Vantage 前先卸载扩展。

Vantage and this overlay are distributed under [GPL-3.0](../../LICENSE).
