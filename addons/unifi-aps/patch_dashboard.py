"""Attach the UniFi AP inventory to the LAN branch of the local Vantage view."""
import hashlib
from pathlib import Path
import sys

EXPECTED = '1ac0f9d2e2500576cda7e0e3c087bff639e45399e1987aa23e6e5f4d50c1778d'


def replace(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Unexpected anchor count for {old[:60]!r}')
    return text.replace(old, new)


def patch(text):
    text = replace(text, 'var callBoard=rpc.declare', '''var callUnifiAps = rpc.declare({ object: 'luci.unifi_aps', method: 'list', expect: { '': {} } });

function appendUnifiAps(branch, snapshot) {
    if (!snapshot || snapshot.state !== 'ok' || !snapshot.aps.length) return;
    branch.wrap.classList.add('vt-branch-unifi');
    var col = E('div', { 'class': 'vt-branch-ssids vt-unifi-list', 'aria-label': 'UniFi AP' });
    snapshot.aps.forEach(function(ap) {
        var node = E('div', { 'class': 'vt-node vt-node-ssid vt-unifi-card', 'title': ap.name }, [
            E('span', { 'class': 'vt-node-body' }, [
                E('span', { 'class': 'vt-node-title' }, [ document.createTextNode(ap.name) ]),
                E('span', { 'class': 'vt-node-sub vt-mono' }, [ document.createTextNode([ap.model, ap.ip].filter(Boolean).join(' · ')) ])
            ])
        ]);
        branch.ssids.push({ id: ap.ip, el: node, active: false });
        col.appendChild(node);
    });
    branch.wrap.appendChild(col);
}

var callBoard=rpc.declare''')
    text = replace(text, 'var started=Date.now(),self=this;return Promise.all([', '''var started=Date.now(),self=this;
if (!self.unifiAt || started - self.unifiAt >= 60000) {
    self.unifiAt = started;
    L.resolveDefault(callUnifiAps(), {}).then(function(reply) {
        self.unifiSnapshot = reply.state === 'ok' && Array.isArray(reply.aps) ?
            { state: 'ok', aps: reply.aps } : { state: 'unavailable', aps: [] };
        if (self.m && self.hero) self.paintHero();
    });
}
return Promise.all([''')
    text = replace(text, ".map(function(n){return n.name;}).join('\\n')+lines;",
                   ".map(function(n){return n.name;}).join('\\n')+lines+'\\nunifi='+JSON.stringify(this.unifiSnapshot||null);")
    text = replace(text, "b.wrap=E('div',{'class':'vt-branch'},[b.el]);h.radios.push(b);",
                   "b.wrap=E('div',{'class':'vt-branch'},[b.el]);if(n.name==='lan')appendUnifiAps(b,self.unifiSnapshot);h.radios.push(b);")
    text = replace(text, "'vantage/app.css')+'?v='+L.env.resource_version",
                   "'vantage/app.css')+'?v='+L.env.resource_version+'&unifi=2'")
    return text


if __name__ == '__main__':
    source, output = map(Path, sys.argv[1:])
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != EXPECTED:
        raise ValueError('Dashboard source changed. Review the patch before applying.')
    output.write_bytes(patch(data.decode('utf-8')).encode('utf-8'))
