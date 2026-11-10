# 接入分类与原生概览

这组可选功能随 [UniFi 扩展](../README.md)安装。Vantage 增加「有线 / Wi-Fi / VPN / 待确认」筛选，将 AP 移到独立 Wi-Fi 分组，并显示已知的交换机端口。「状态 → 概览」可使用同一份 `home-network/access.js`。手动别名优先，其次是 UniFi 名称，再回到原来的设备名称或地址。

## 安装

当前适配 OpenWrt 25.12、原版上游 `luci-app-vantage 1.0.16-r1` APK 和 Vantage 的有线仪表盘视图。支持与路由器同机、具备旧版 `mongo` 命令的 UniFi Docker 容器。按 [UniFi 扩展说明](../README.md)准备 Python 和容器。如果此前已经安装过旧版 UniFi 扩展，先用旧版的卸载命令还原它。要使用这次的新功能，从本仓库的对应提交获取整个 `addons/unifi-aps` 目录。

在路由器上，以管理员身份从该目录执行：

```sh
python3 -B install.py install --container unifi-network --home-access
```

将 `unifi-network` 换成实际容器名。加 `--native-overview` 会同时把客户端列表安装到 LuCI 自带的概览扩展目录。它也隐含 `--home-access`。安装器核对 Vantage 文件校验值、AP 采集器和所选的概览加载入口。手工定制过的活动页面应按各自的部署顺序恢复。

| 可选参数 | 用途 |
|---|---|
| `--lan-interface lan --lan-bridge br-lan` | OpenWrt 逻辑 LAN 和对应 Linux 网桥。示例为默认值。 |
| `--switch-uplink lan2 --switch-label 'Example switch'` | 路由器通往交换机的网口和显示名称。需要下方的交换机数据源。 |
| `--openvpn-status /var/run/openvpn/server.status` | 指向已有的 OpenVPN 状态文件。使用版本 2 或 3，建议 60 秒写一次。示例路径需替换。 |

### 可选数据源

- **交换机**需要已有的 `luci.vantage_switch.snapshot` 只读接口。成功响应包含 `state: "ok"` 和 `clients`，后者把小写 MAC 映射到端口名。提供 `ports` 数组时，原生概览还可展示端口状态及收发速率。分类会用交换机端口交叉核对 UniFi 的最近关联。数据源缺失或证据不完整时，仍可看到最近 AP 和已知链路，相关客户端归入「待确认」。
- **上网计数**可复用 `luci.vantage_internet.counters`，响应为 `at` 采样时间和 `hosts` 地址到 `rx`、`tx` 累计字节数的映射。此接口用于原生概览，未安装时仍可显示桥上已学习的设备。标准 Vantage 继续使用自身的实时流量列。
- **VPN**由扩展的 `luci.home_access.vpn` 提供，读取已配置的状态文件，只返回会话名称、隧道地址和拓扑显示参数。VPN 行的速率留空。自定义 LuCI 账号需要 `luci-home-access` 的读取权限才能获取拓扑参数和 VPN 会话。UniFi 清单仍使用 `luci-unifi-aps` 读取组。

## 升级与恢复

1. 保存本次使用的提交、安装参数、`/etc/vantage-unifi-aps.json` 以及独立的数据源配置。凭据单独保存。
2. 升级 Vantage 软件包前，使用当前扩展目录中的 `python3 -B install.py uninstall` 还原。Vantage 的原始页面和样式备份在 `/etc/vantage-unifi-aps-backup`。如果其他工具后来改过相关文件，卸载会拒绝覆盖或移除冲突文件。
3. 恢复目标版本的 Vantage、UniFi 容器和可选采集服务，再用兼容目标版本的扩展和原来的参数安装。遇到校验不匹配时，先为目标构建重新适配补丁。
4. 登录后分别检查四类筛选、直连端口、AP 分组和 VPN 会话。若启用了原生概览，再检查别名、最近 AP 和回退显示。
