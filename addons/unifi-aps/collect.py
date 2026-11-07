"""Read adopted AP inventory for LuCI from the local UniFi controller."""
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time

CACHE_DIR = Path('/tmp/luci-unifi-aps')
CONFIG = Path('/etc/vantage-unifi-aps.json')
DOCKER_NAME = re.compile(r'[a-zA-Z0-9][a-zA-Z0-9_.-]{0,127}')
TTL = 60
UNAVAILABLE = {'state': 'unavailable', 'aps': []}
QUERY = '''print(JSON.stringify(db.device.find({adopted:true,type:"uap"},
    {_id:0,name:1,model:1,ip:1}).limit(33).maxTimeMS(1500).toArray()))'''


def read_json(args, timeout):
    raw = subprocess.check_output(args, stderr=subprocess.DEVNULL, timeout=timeout)
    return json.loads(raw)


def read_controller(container=None):
    if container is None:
        container = json.loads(CONFIG.read_bytes())['container']
    if not isinstance(container, str) or not DOCKER_NAME.fullmatch(container):
        raise ValueError('Invalid Docker container name')
    lan = read_json(['/sbin/ifstatus', 'lan'], 2)
    subnets = [ipaddress.IPv4Network((a['address'], a['mask']), strict=False)
               for a in lan['ipv4-address']]
    if not subnets:
        raise ValueError('LAN has no IPv4 network')
    rows = read_json(['/usr/bin/docker', 'exec', container, 'mongo', '--norc', '--quiet',
                      '--port', '27117', 'ace', '--eval', QUERY], 4)
    if not isinstance(rows, list) or len(rows) > 32:
        raise ValueError('Unexpected device count')
    aps = {}
    for row in rows:
        try:
            address = ipaddress.IPv4Address(row['ip'])
        except (KeyError, ValueError, TypeError):
            continue
        if not any(address in network for network in subnets):
            continue
        name = row.get('name') or 'UniFi AP'
        model = row.get('model') or ''
        if not isinstance(name, str) or not isinstance(model, str):
            continue
        aps[address] = {'name': re.sub(r'[\x00-\x1f\x7f]', '', name).strip()[:64] or 'UniFi AP',
                        'model': model[:24], 'ip': str(address)}
    return {'state': 'ok', 'aps': [aps[ip] for ip in sorted(aps)]}


def sample():
    import fcntl

    CACHE_DIR.mkdir(mode=0o700, exist_ok=True)
    info = CACHE_DIR.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('Unsafe cache directory')
    cache = CACHE_DIR / 'inventory.json'
    fd = os.open(CACHE_DIR / 'lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd) as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return UNAVAILABLE
        now = time.monotonic()
        if cache.exists():
            saved = json.loads(cache.read_bytes())
            if 0 <= now - saved['sampled'] < TTL:
                return saved['result']
        try:
            result = read_controller()
        except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
            result = UNAVAILABLE
        with tempfile.NamedTemporaryFile(dir=CACHE_DIR, delete=False) as pending:
            tmp = Path(pending.name)
            try:
                pending.write(json.dumps({'sampled': now, 'result': result}).encode())
                pending.close()
                os.replace(tmp, cache)
            finally:
                tmp.unlink(missing_ok=True)
        return result


if __name__ == '__main__':
    try:
        print(json.dumps(sample()))
    except (OSError, ValueError, KeyError, TypeError):
        print(json.dumps(UNAVAILABLE))
