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
    {_id:0,name:1,model:1,ip:1,mac:1}).limit(33).maxTimeMS(1500).toArray()))'''
MAC = re.compile(r'(?:[0-9a-f]{2}:){5}[0-9a-f]{2}', re.I)


def read_json(args, timeout):
    raw = subprocess.check_output(args, stderr=subprocess.DEVNULL, timeout=timeout)
    return json.loads(raw)


def query_controller(container, query):
    return read_json(['/usr/bin/docker', 'exec', container, 'mongo', '--norc', '--quiet',
                      '--port', '27117', 'ace', '--eval', query], 4)


def read_clients(container, bridge, subnets, ap_names):
    if not bridge or not ap_names:
        return {}
    fdb = subprocess.check_output(['/usr/sbin/brctl', 'showmacs', bridge],
                                  stderr=subprocess.DEVNULL, text=True, timeout=2)
    hosts = []
    for line in fdb.splitlines()[1:]:
        fields = line.split()
        if len(fields) != 4 or fields[2] != 'no' or not MAC.fullmatch(fields[1]):
            continue
        age = float(fields[3])
        if 0 <= age <= 300:
            hosts.append((age, fields[1].lower()))
    macs = list(dict.fromkeys(mac for _, mac in sorted(hosts)))[:96]
    if not macs:
        return {}
    query = '''print(JSON.stringify(db.user.find({is_wired:false,mac:{$in:%s}},
        {_id:0,mac:1,last_ip:1,last_uplink_mac:1,name:1,hostname:1})
        .sort({last_seen:-1}).limit(192).maxTimeMS(1500).toArray()))''' % json.dumps(macs)
    clients = {}
    for row in query_controller(container, query):
        mac = row.get('mac')
        ap = ap_names.get(row.get('last_uplink_mac'))
        if mac not in macs or mac in clients or not ap:
            continue
        try:
            address = ipaddress.IPv4Address(row['last_ip'])
        except (KeyError, ValueError, TypeError):
            continue
        if any(address in subnet for subnet in subnets):
            name = row.get('name') or row.get('hostname') or ''
            name = re.sub(r'[\x00-\x1f\x7f]', '', name).strip()[:48] if isinstance(name, str) else ''
            clients[mac] = {'ap': ap, 'name': name}
    return clients


def read_controller(container=None, config=None):
    if container is None:
        config = json.loads(CONFIG.read_bytes())
        container = config['container']
    if not isinstance(container, str) or not DOCKER_NAME.fullmatch(container):
        raise ValueError('Invalid Docker container name')
    config = config or {}
    topology = config.get('topology', {})
    lan = read_json(['/sbin/ifstatus', topology.get('lan_interface', 'lan')], 2)
    subnets = [ipaddress.IPv4Network((a['address'], a['mask']), strict=False)
               for a in lan['ipv4-address']]
    if not subnets:
        raise ValueError('LAN has no IPv4 network')
    rows = query_controller(container, QUERY)
    if not isinstance(rows, list) or len(rows) > 32:
        raise ValueError('Unexpected device count')
    aps, ap_names = {}, {}
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
        if MAC.fullmatch(row.get('mac') or ''):
            ap_names[row['mac'].lower()] = aps[address]['name']
    result = {'state': 'ok', 'aps': [aps[ip] for ip in sorted(aps)]}
    if config.get('home_access'):
        try:
            clients = read_clients(container, topology.get('lan_bridge') or lan.get('device'), subnets, ap_names)
        except (OSError, ValueError, TypeError, AttributeError, subprocess.SubprocessError):
            clients = {}
        result['clients'] = clients
        while clients and len(json.dumps(result)) >= 16384:
            clients.popitem()
    return result


def sample():
    import fcntl

    CACHE_DIR.mkdir(mode=0o700, exist_ok=True)
    info = CACHE_DIR.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise ValueError('Unsafe cache directory')
    cache = CACHE_DIR / 'inventory-v2.json'
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
