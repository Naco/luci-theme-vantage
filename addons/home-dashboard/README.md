# Household dashboard overlay for 1.0.19

This optional overlay preserves the existing household dashboard while installing
the official Vantage 1.0.19 APKs. The ordinary fork package remains usable without
external controllers. This overlay requires the already deployed household
providers; it does not install or configure a switch, controller, VPN or firewall.

It retains switch port totals, per-client Internet throughput, UniFi client names
(manual aliases first), four access categories, the separate Wi-Fi branch linked
to the LAN switch, the OpenVPN branch, Docker bridge filtering, SI byte rates,
and direct dashboard access under Bootstrap. Low-power polling and other upstream
1.0.19 improvements remain. Physical link speeds still use bit/s.

Required existing interfaces:

- `luci.vantage_switch.snapshot`: port rates and MAC-to-port mapping.
- `luci.vantage_internet.counters`: per-client Internet byte counters.
- `luci.unifi_aps.list`: AP inventory and client names/AP associations.
- `luci.home_access.vpn` and `home-network/access.js`: shared access classification.
- The matching existing read-only RPC ACLs. No credentials belong in this tree.

The household adapter uses `lan`, switch uplink `eth0`, and OpenVPN `tunhome`.
Other installations must adapt those names and the shared classifier first. The
older `addons/unifi-aps/install.py` targets 1.0.16 and must not be forced onto
1.0.19 by bypassing its hash checks.

## Prepare

Download the four APKs from the official
[1.0.19 release](https://github.com/anothaDev/luci-theme-vantage/releases/tag/v1.0.19)
and check `.release-manifests/v1.0.19.sha256`. OpenWrt signs repository indexes;
these individual release APKs are unsigned. Extract them to a staging directory.

```sh
python3 addons/home-dashboard/apply.py --stock /tmp/vantage-stock --output /tmp/vantage-patched
```

`v1.0.19-apk.json` contains bounded textual edits with exact input and output
SHA-256 checks. The tool validates all four inputs before writing output and
never modifies the source tree in place. No formatter or npm dependency is needed
to apply it. It changes only the dashboard, formatting/model modules and app CSS.

Preview the generated files using the replay with a real rootfs and sanitized
read-only recording. Test Vantage and Bootstrap, port samples, the Wi-Fi/AP path,
category filters, aliases, VPN clients and byte-rate chart labels. Captured wired
clients are retained by the replay in `--no-synthetic` mode.

## Deploy and recover

Before deploying, retain the previous APKs and the actual installed files/configs,
including local patches. Stage and check the complete new output first. Upgrade
only the four Vantage packages, then replace the four generated files atomically;
retain existing provider ACLs, configurations and the native Overview component.
Reload rpcd for the new upstream plugin and verify authenticated calls and pages.
No router reboot or network restart is needed.

On failure, reinstall the retained previous packages and restore the captured
files/configs. Do not treat reinstalling an unmodified old theme as a complete
rollback: it would omit the household customizations. Backend data collection
and Docker containers are independent and should keep running throughout.

Upstream 1.0.19 includes read-only `iwinfo.survey` permission and the optional
validated `luci.vantage.set_quiet` operation for muting signal warnings. This
overlay uses the existing household read-only groups and adds no write authority.
