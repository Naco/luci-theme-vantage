"""Install the UniFi inventory overlay on a supported Vantage release."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import runpy
import subprocess
import tempfile

from collect import CONFIG, DOCKER_NAME, read_controller
from patch_dashboard import EXPECTED, patch

HERE = Path(__file__).resolve().parent
BACKUP = Path('/etc/vantage-unifi-aps-backup')
VIEW = Path('/www/luci-static/resources/view/vantage/overview.js')
STYLE = Path('/www/luci-static/resources/vantage/app.css')
HELPERS = {
    Path('/usr/libexec/luci-unifi-aps.py'): 'collect.py',
    Path('/usr/share/rpcd/ucode/luci.unifi_aps'): 'luci.unifi_aps',
    Path('/usr/share/rpcd/acl.d/luci-unifi-aps.json'): 'luci-unifi-aps.json',
}
STYLE_SHA = 'c8735854cca279ee04ce0bfd8765ba0efa058791e0f34e96d1f5983518f2ff79'
NATIVE = Path('/www/luci-static/resources/view/status/include/15_home_network.js')
HOME_HELPERS = {
    Path('/www/luci-static/resources/home-network/access.js'): 'home-access/access.js',
    Path('/usr/libexec/luci-home-access-vpn.py'): 'home-access/vpn_status.py',
    Path('/usr/share/rpcd/ucode/luci.home_access'): 'home-access/luci.home_access',
    Path('/usr/share/rpcd/acl.d/luci-home-access.json'): 'home-access/luci-home-access.json',
}
INTERFACE = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,31}')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def write(path, data, mode=0o644):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as pending:
        tmp = Path(pending.name)
        try:
            pending.write(data)
            pending.close()
            tmp.chmod(mode)
            tmp.replace(path)
        finally:
            tmp.unlink(missing_ok=True)


def build(view, style, home_access=False):
    if digest(view) != EXPECTED or digest(style) != STYLE_SHA:
        raise ValueError('Vantage files differ from the supported 1.0.16-r1 build.')
    page = patch(view.decode())
    if home_access:
        overlay = runpy.run_path(str(HERE / 'home-access/patch_vantage.py'))
        if digest(page.encode()) != overlay['EXPECTED']:
            raise ValueError('Unexpected UniFi overlay version for home access.')
        page = overlay['patch'](page)
    return (page.encode(), style + b'\n' + (HERE / 'unifi-aps.css').read_bytes())


def reload_rpcd():
    subprocess.run(['/etc/init.d/rpcd', 'reload'], check=True, timeout=20)


def restore():
    manifest = json.loads((BACKUP / 'manifest.json').read_bytes())
    originals = {p: (BACKUP / p.name).read_bytes() for p in (VIEW, STYLE)}
    extras = manifest.get('extras', {})
    allowed = {str(p) for p in (*HOME_HELPERS, NATIVE)}
    if not set(extras) <= allowed:
        raise ValueError('Unexpected home access manifest entry.')
    for name, expected in extras.items():
        path = Path(name)
        if path.is_symlink() or (path.exists() and digest(path.read_bytes()) != expected):
            raise ValueError(f'{path} changed after installation. Refusing to remove it.')
    for path, original in originals.items():
        if digest(path.read_bytes()) not in {digest(original), manifest[str(path)]}:
            raise ValueError(f'{path} changed after installation. Refusing to replace it.')
    for path, original in originals.items():
        write(path, original)
    for path in (*HELPERS, CONFIG, *map(Path, extras)):
        path.unlink(missing_ok=True)
    reload_rpcd()
    for name in (VIEW.name, STYLE.name, 'manifest.json'):
        (BACKUP / name).unlink()
    BACKUP.rmdir()


def install(container, home_access=False, native_overview=False, topology=None, openvpn_status=None):
    if not DOCKER_NAME.fullmatch(container):
        raise ValueError('Specify a local Docker container name.')
    home_access = home_access or native_overview
    extra = dict(HOME_HELPERS) if home_access else {}
    if native_overview:
        index = NATIVE.parent.parent / 'index.js'
        if not NATIVE.parent.is_dir() or b'view/status/include' not in index.read_bytes():
            raise ValueError('This LuCI Overview does not load extension modules.')
        extra[NATIVE] = 'home-access/15_home_network.js'
    if any(p.exists() or p.is_symlink() for p in (BACKUP, *HELPERS, CONFIG, *extra)):
        raise ValueError('An overlay or recovery files already exist. Remove that installation first.')
    view, style = VIEW.read_bytes(), STYLE.read_bytes()
    new_view, new_style = build(view, style, home_access)
    config = {'container': container}
    if home_access:
        config.update(home_access=True, topology=topology or {})
        if openvpn_status:
            config['openvpn_status'] = str(openvpn_status)
        snapshot = read_controller(container, config)
    else:
        snapshot = read_controller(container)
    payloads = {path: (HERE / source).read_bytes().replace(b'\r\n', b'\n')
                for path, source in {**HELPERS, **extra}.items()}
    print(f"Controller preflight found {len(snapshot['aps'])} AP(s) in LAN.")
    BACKUP.mkdir(mode=0o700)
    write(BACKUP / VIEW.name, view, 0o600)
    write(BACKUP / STYLE.name, style, 0o600)
    write(BACKUP / 'manifest.json', json.dumps({
        str(VIEW): digest(new_view), str(STYLE): digest(new_style),
        'extras': {str(path): digest(payloads[path]) for path in extra},
    }).encode(), 0o600)
    try:
        write(CONFIG, json.dumps(config).encode(), 0o600)
        for path, data in payloads.items():
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
            write(path, data)
        reload_rpcd()
        result = subprocess.check_output(
            ['/bin/ubus', 'call', 'luci.unifi_aps', 'list', '{}'], timeout=10)
        snapshot = json.loads(result)
        if not isinstance(snapshot, dict) or snapshot.get('state') != 'ok':
            raise ValueError('The installed AP inventory RPC did not return a usable result.')
        if home_access:
            result = subprocess.check_output(['/bin/ubus', 'call', 'luci.home_access', 'vpn', '{}'], timeout=10)
            snapshot = json.loads(result)
            if not isinstance(snapshot, dict) or 'topology' not in snapshot or not isinstance(snapshot.get('clients'), list):
                raise ValueError('The installed home access RPC did not return a usable result.')
        write(STYLE, new_style)
        write(VIEW, new_view)
    except (OSError, ValueError, subprocess.SubprocessError):
        restore()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    add = commands.add_parser('install')
    add.add_argument('--container', required=True)
    add.add_argument('--home-access', action='store_true')
    add.add_argument('--native-overview', action='store_true')
    add.add_argument('--lan-interface', default='lan')
    add.add_argument('--lan-bridge', default='br-lan')
    add.add_argument('--switch-uplink', default='')
    add.add_argument('--switch-label', default='Switch')
    add.add_argument('--openvpn-status', type=Path)
    commands.add_parser('uninstall')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.exit(1, 'Run on OpenWrt as root.\n')
    try:
        if args.command == 'install':
            if not all(INTERFACE.fullmatch(v) for v in (args.lan_interface, args.lan_bridge)) or (
                    args.switch_uplink and not INTERFACE.fullmatch(args.switch_uplink)):
                raise ValueError('Invalid LAN or switch interface name.')
            if not 1 <= len(args.switch_label) <= 48 or not args.switch_label.isprintable():
                raise ValueError('Invalid switch display name.')
            if args.openvpn_status is not None and not args.openvpn_status.is_absolute():
                raise ValueError('Specify an absolute OpenVPN status file path.')
            topology = {'lan_interface': args.lan_interface, 'lan_bridge': args.lan_bridge,
                        'switch_uplink': args.switch_uplink, 'switch_label': args.switch_label}
            install(args.container, args.home_access, args.native_overview, topology, args.openvpn_status)
        else:
            restore()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f'{error}\n')
    print('Done. Reload the LuCI dashboard.')


if __name__ == '__main__':
    main()
