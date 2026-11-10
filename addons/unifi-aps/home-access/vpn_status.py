"""Project only current OpenVPN client names and tunnel addresses for LuCI."""
import csv
import ipaddress
import json
from os import fstat
from pathlib import Path
import re
import time

CONFIG = Path('/etc/vantage-unifi-aps.json')


def snapshot(path):
    if not path.is_file():
        raise ValueError('OpenVPN status is not a regular file')
    with path.open(encoding='utf-8', errors='replace', newline='') as handle:
        age = time.time() - fstat(handle.fileno()).st_mtime
        content = handle.read(65537)
    if not 0 <= age <= 130 or len(content) > 65536 or not content.rstrip().endswith('\nEND'):
        raise ValueError('OpenVPN status unavailable or stale')
    delimiter = '\t' if content.startswith('TITLE\t') else ','
    clients = {}
    fields = None
    for row in csv.reader(content.splitlines(), delimiter=delimiter):
        if row[:2] == ['HEADER', 'CLIENT_LIST']:
            fields = row[2:]
        elif row[:1] == ['CLIENT_LIST'] and fields:
            entry = dict(zip(fields, row[1:]))
            address = entry.get('Virtual Address') or entry.get('Virtual IPv6 Address')
            try:
                address = str(ipaddress.ip_address(address))
            except ValueError:
                continue
            name = re.sub(r'[\x00-\x1f\x7f]', '', entry.get('Common Name', '')).strip()[:48]
            clients[address] = {'ip': address, 'name': name}
            if len(clients) == 128:
                break
    if fields is None:
        raise ValueError('OpenVPN client header unavailable')
    return {'state': 'ok', 'clients': list(clients.values())}


if __name__ == '__main__':
    data = {'state': 'unavailable', 'clients': []}
    try:
        config = json.loads(CONFIG.read_bytes())
        if config.get('openvpn_status'):
            try:
                data = snapshot(Path(config['openvpn_status']))
            except (OSError, ValueError):
                pass
        data['topology'] = config.get('topology', {})
    except (OSError, ValueError, TypeError, AttributeError):
        pass
    print(json.dumps(data, ensure_ascii=False))
