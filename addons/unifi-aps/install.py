"""Install the UniFi inventory overlay on a supported Vantage release."""
import argparse
import hashlib
import json
import os
from pathlib import Path
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


def build(view, style):
    if digest(view) != EXPECTED or digest(style) != STYLE_SHA:
        raise ValueError('Vantage files differ from the supported 1.0.16-r1 build.')
    return (patch(view.decode()).encode(), style + b'\n' + (HERE / 'unifi-aps.css').read_bytes())


def reload_rpcd():
    subprocess.run(['/etc/init.d/rpcd', 'reload'], check=True, timeout=20)


def restore():
    manifest = json.loads((BACKUP / 'manifest.json').read_bytes())
    originals = {p: (BACKUP / p.name).read_bytes() for p in (VIEW, STYLE)}
    for path, original in originals.items():
        if digest(path.read_bytes()) not in {digest(original), manifest[str(path)]}:
            raise ValueError(f'{path} changed after installation. Refusing to replace it.')
    for path, original in originals.items():
        write(path, original)
    for path in (*HELPERS, CONFIG):
        path.unlink(missing_ok=True)
    reload_rpcd()
    for name in (VIEW.name, STYLE.name, 'manifest.json'):
        (BACKUP / name).unlink()
    BACKUP.rmdir()


def install(container):
    if not DOCKER_NAME.fullmatch(container):
        raise ValueError('Specify a local Docker container name.')
    if any(p.exists() or p.is_symlink() for p in (BACKUP, *HELPERS, CONFIG)):
        raise ValueError('An overlay or recovery files already exist. Remove that installation first.')
    view, style = VIEW.read_bytes(), STYLE.read_bytes()
    new_view, new_style = build(view, style)
    snapshot = read_controller(container)
    print(f"Controller preflight found {len(snapshot['aps'])} AP(s) in LAN.")
    BACKUP.mkdir(mode=0o700)
    write(BACKUP / VIEW.name, view, 0o600)
    write(BACKUP / STYLE.name, style, 0o600)
    write(BACKUP / 'manifest.json', json.dumps({
        str(VIEW): digest(new_view), str(STYLE): digest(new_style)
    }).encode(), 0o600)
    try:
        write(CONFIG, json.dumps({'container': container}).encode(), 0o600)
        for path, source in HELPERS.items():
            write(path, (HERE / source).read_bytes().replace(b'\r\n', b'\n'))
        reload_rpcd()
        result = subprocess.check_output(
            ['/bin/ubus', 'call', 'luci.unifi_aps', 'list', '{}'], timeout=10)
        snapshot = json.loads(result)
        if not isinstance(snapshot, dict) or snapshot.get('state') != 'ok':
            raise ValueError('The installed AP inventory RPC did not return a usable result.')
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
    commands.add_parser('uninstall')
    args = parser.parse_args()
    if os.geteuid() != 0:
        parser.exit(1, 'Run on OpenWrt as root.\n')
    try:
        if args.command == 'install':
            install(args.container)
        else:
            restore()
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(1, f'{error}\n')
    print('Done. Reload the LuCI dashboard.')


if __name__ == '__main__':
    main()
