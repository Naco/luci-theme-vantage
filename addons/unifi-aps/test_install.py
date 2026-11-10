"""Exercise install and rollback against an offline router directory."""
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

import install

view_source, style_source = [Path(p).read_bytes() for p in sys.argv[1:]]
with tempfile.TemporaryDirectory() as work:
    root = Path(work)
    view, style, config = [root / name for name in ('overview.js', 'app.css', 'config.json')]
    helpers = {root / Path(p).name: name for p, name in install.HELPERS.items()}
    replacements = dict(VIEW=view, STYLE=style, CONFIG=config, HELPERS=helpers, BACKUP=root / 'backup')
    with patch.multiple(install, **replacements), patch.object(install, 'reload_rpcd'), \
            patch.object(install, 'read_controller', return_value={'aps': [{}]}) as inventory, \
            patch.object(install.subprocess, 'check_output', return_value=b'{"state":"ok"}') as rpc:
        style.write_bytes(style_source)
        view.write_bytes(b'unsupported')
        try:
            install.install('unifi-test')
        except ValueError:
            pass
        else:
            raise AssertionError('Unsupported dashboard accepted')
        assert not config.exists() and not inventory.called

        view.write_bytes(view_source)
        install.install('unifi-test')
        assert b'vt-unifi-card' in view.read_bytes()
        assert b'vt-branch-unifi' in style.read_bytes()
        with tempfile.NamedTemporaryFile(suffix='.js', delete=False) as script:
            script.write(view.read_bytes())
        try:
            subprocess.run(['node', '--check', script.name], check=True)
        finally:
            Path(script.name).unlink()

        install.restore()
        assert view.read_bytes() == view_source and style.read_bytes() == style_source
        assert not any(p.exists() for p in (install.BACKUP, config, *helpers))

        native = root / 'status/include/15_home_network.js'
        native.parent.mkdir(parents=True)
        (native.parent.parent / 'index.js').write_text('view/status/include')
        home_helpers = {root / path.name: source for path, source in install.HOME_HELPERS.items()}
        topology = {'lan_interface': 'lan', 'lan_bridge': 'br-lan', 'switch_uplink': 'lan2', 'switch_label': 'Example switch'}
        with patch.multiple(install, HOME_HELPERS=home_helpers, NATIVE=native):
            rpc.side_effect = [b'{"state":"ok"}', b'{"state":"unavailable","topology":{},"clients":[]}']
            install.install('unifi-test', native_overview=True, topology=topology)
            assert b"require home-network.access as homeAccess" in view.read_bytes()
            assert b"require home-network.access as access" in native.read_bytes()
            assert b"vt-home-wifi" in view.read_bytes()
            subprocess.run(['node', '--check', str(view)], check=True)
            subprocess.run(['node', '--check', str(native)], check=True)
            edited = native.read_bytes()
            native.write_bytes(edited + b'\n')
            try:
                install.restore()
            except ValueError:
                pass
            else:
                raise AssertionError('Modified native overview accepted for rollback')
            native.write_bytes(edited)
            install.restore()
            assert view.read_bytes() == view_source and style.read_bytes() == style_source
            assert not any(p.exists() for p in (install.BACKUP, config, native, *helpers, *home_helpers))

            rpc.side_effect = [b'{"state":"ok"}', b'{}']
            try:
                install.install('unifi-test', native_overview=True)
            except ValueError:
                pass
            else:
                raise AssertionError('Failed home access RPC accepted')
            assert view.read_bytes() == view_source and style.read_bytes() == style_source
            assert not any(p.exists() for p in (install.BACKUP, config, native, *helpers, *home_helpers))
            rpc.side_effect = None

        rpc.return_value = b'{"state":"unavailable"}'
        try:
            install.install('unifi-test')
        except ValueError:
            pass
        else:
            raise AssertionError('Failed RPC accepted')
        assert view.read_bytes() == view_source and style.read_bytes() == style_source
        assert not any(p.exists() for p in (install.BACKUP, config, *helpers))

print('Version rejection, install, JS syntax, uninstall and failed RPC rollback passed.')
