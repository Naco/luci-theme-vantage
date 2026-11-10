"""Apply the access categories and Wi-Fi branch to the household dashboard."""
from hashlib import sha256
from pathlib import Path
import sys

EXPECTED = '1d54ffb6b55f63994a77319ad57ea875a690afdaa822c6718f0952b5149dfcfb'


def patch(text):
    def replace(old, new):
        nonlocal text
        if text.count(old) != 1:
            raise ValueError(f'Unexpected anchor count for {old[:100]!r}')
        text = text.replace(old, new)

    replace("'require rpc';", "'require rpc';\n'require home-network.access as homeAccess';")
    start = text.index('function appendUnifiAps(')
    end = text.index('var callBoard', start)
    text = text[:start] + '''var callHomeVpn = rpc.declare({ object: 'luci.home_access', method: 'vpn', expect: { '': {} } });

var callHomeSwitch = rpc.declare({ object: 'luci.vantage_switch', method: 'snapshot', expect: { '': {} } });

function switchWord(zh, en) {
    return /^zh(?:[-_]|$)/i.test(document.documentElement.lang || '') ? zh : en;
}

function homeContext(view) {
    var raw = view.lastRaw || {}, snapshot = view.unifiSnapshot || {};
    return homeAccess.prepare(raw.fdb, view.switchSnapshot,
        { aps: snapshot.aps, clients: snapshot.clients }, raw.hints, view.homeVpn && view.homeVpn.topology);
}

function homePathKey(view) {
    var context = homeContext(view);
    return JSON.stringify([context.aps, context.lanInterface, context.switchUplink, context.switchLabel]);
}

function homeAccessLabel(kind) {
    return homeAccess.label(kind, switchWord);
}

function homeClientKinds(view, rows) {
    var selected = view.ui.accessKind || 'all';
    var kinds = [ 'all' ].concat(homeAccess.kinds);
    var counts = { all: rows.length, wired: 0, wifi: 0, vpn: 0, unknown: 0 };
    rows.forEach(function(row) { counts[row.connection.kind]++; });
    var signature = selected + ' ' + kinds.map(function(kind) { return counts[kind]; }).join(' ');
    if (view.kindSig === signature) return;
    view.kindSig = signature;
    dom.content(view.el.kinds, kinds.map(function(kind) {
        return E('button', { 'type': 'button', 'class': 'vt-kind' + (kind === selected ? ' vt-kind-on' : ''),
            'aria-pressed': String(kind === selected), 'click': function() {
                view.ui.accessKind = kind;
                view.ui.chip = 'all';
                view.pickClients();
            } }, [ E('span', {}, [ kind === 'all' ? _('All') : homeAccessLabel(kind) ]),
                E('span', { 'class': 'vt-kind-n vt-tn' }, [ String(counts[kind]) ]) ]);
    }));
}

function appendHomeWifi(hero, context, view) {
    if (!context.aps.length) return;
    var lan = hero.radios.find(function(branch) { return branch.id === context.lanInterface; });
    var branch = { id: 'home-wifi', ssids: [], via: lan && lan.el };
    branch.el = E('button', { 'type': 'button', 'class': 'vt-node vt-node-radio vt-node-net',
        'click': function() { view.ui.accessKind = 'wifi'; view.showWired(); } }, [
        E('span', { 'class': 'vt-node-body' }, [
            E('span', { 'class': 'vt-node-title' }, [ 'Wi-Fi' ]),
            E('span', { 'class': 'vt-node-sub' }, [ context.switchUplink ? switchWord('经交换机接入 LAN · ', 'LAN via ') + context.switchLabel :
                switchWord('接入 LAN', 'LAN uplink') ])
        ])
    ]);
    var col = E('div', { 'class': 'vt-branch-ssids vt-unifi-list', 'aria-label': 'UniFi AP' });
    context.aps.forEach(function(ap) {
        var caption = [ ap.port ? context.switchLabel + ' · ' + ap.port : '', ap.model, ap.ip ].filter(Boolean).join(' · ');
        var node = E('div', { 'class': 'vt-node vt-node-ssid vt-unifi-card', 'title': caption }, [
            E('span', { 'class': 'vt-node-body' }, [
                E('span', { 'class': 'vt-node-title' }, [ document.createTextNode(ap.name) ]),
                E('span', { 'class': 'vt-node-sub vt-mono' }, [ document.createTextNode(caption) ])
            ])
        ]);
        branch.ssids.push({ id: ap.ip, el: node, active: false });
        col.appendChild(node);
    });
    branch.wrap = E('div', { 'class': 'vt-branch vt-branch-unifi vt-home-wifi' }, [ branch.el, col ]);
    var position = lan ? hero.radios.indexOf(lan) + 1 : hero.radios.length;
    hero.radios.splice(position, 0, branch);
}

''' + text[end:]

    replace('if (!self.unifiAt || started - self.unifiAt >= 60000) {', '''if (!self.homeVpnAt || started - self.homeVpnAt >= 15000) {
    self.homeVpnAt = started;
    L.resolveDefault(callHomeVpn(), {}).then(function(reply) { self.homeVpn = reply; });
}
if (self.homeVpn?.topology?.switch_uplink && (!self.homeSwitchAt || started - self.homeSwitchAt >= 5000)) {
    self.homeSwitchAt = started;
    L.resolveDefault(callHomeSwitch(), {}).then(function(reply) { self.switchSnapshot = reply; });
}
if (!self.unifiAt || started - self.unifiAt >= 60000) {''')
    replace("{ state: 'ok', aps: reply.aps }", "{ state: 'ok', aps: reply.aps, clients: reply.clients || {} }")
    replace("lines+'\\nunifi='+JSON.stringify(this.unifiSnapshot||null)", "lines+'\\nunifi='+homePathKey(this)")
    replace("if(n.name==='lan')appendUnifiAps(b,self.unifiSnapshot);h.radios.push(b);});",
            "h.radios.push(b);});appendHomeWifi(h,homeContext(this),this);")
    replace("txt(b.kicker,n.proto||_('Interface'));txt(b.title,n.name);",
            "txt(b.kicker,n.name===(self.homeVpn?.topology?.lan_interface||'lan')?'LAN':n.proto||_('Interface'));txt(b.title,n.name===(self.homeVpn?.topology?.lan_interface||'lan')?switchWord('有线','Wired'):n.name);")
    replace("key:'r:'+b.id,from:h.ap,to:b.el", "key:'r:'+b.id,from:b.via||h.ap,to:b.el")
    replace("var wired=ui.kind==='wired',all=wired?hosts:m.clients;el.kinds.hidden=!both;var kindSig=both?",
            """var wired=ui.kind==='wired',all=wired?hosts:m.clients;
if (m.wired) {
    all = all.concat(homeAccess.vpnRows(this.homeVpn));
    var context = homeContext(this);
    all.forEach(function(client) {
        var match = context.clients[client.mac];
        var label = match && fmt.safeText(match.name || '', 48);
        if (label && client.nameSource !== 'alias') {
            client.name = client.plainName = label;
            client.nameSource = 'unifi';
            client.nameSourceLabel = 'UniFi';
        }
        client.connection = homeAccess.classify(client, context, switchWord);
    });
    el.kinds.hidden = false;
    homeClientKinds(this, all);
} else el.kinds.hidden=!both;
var kindSig=both?""")
    replace("if(this.kindSig!==kindSig){this.kindSig=kindSig;",
            "if(!m.wired&&this.kindSig!==kindSig){this.kindSig=kindSig;")
    replace("['net',_('Network')],['live',_('Live')]",
            "['net',m.wired?switchWord('接入方式','Access'):_('Network')],['live',_('Live')]")
    replace("var list=all.filter(L.bind(this.matches,this));",
            "var list=all.filter(function(c){return (!m.wired||!ui.accessKind||ui.accessKind==='all'||c.connection.kind===ui.accessKind)&&self.matches(c);});")
    replace("case'link':return c.shared", "case'link':if(c.connection)return c.connection.link.toLowerCase();return c.shared")
    replace("case'net':return((c.network", "case'net':if(c.connection)return c.connection.kind;return((c.network")
    replace("if(!q)return true;hay=hay.concat(c.ips||[])", "if(c.vpn&&/^port:/.test(chip))return false;if(!q)return true;if(c.connection)hay.push(c.connection.link,c.connection.detail,homeAccessLabel(c.connection.kind));hay=hay.concat(c.ips||[])")
    replace("tr.addEventListener('click',function(){self.openDrawer", "if(!c.vpn)tr.addEventListener('click',function(){self.openDrawer")
    replace("tr.addEventListener('keydown',function(ev){if(ev.key", "if(!c.vpn)tr.addEventListener('keydown',function(ev){if(ev.key")
    replace("'tabindex':'0'});if(!c.vpn)tr.addEventListener", "'tabindex':c.vpn?'-1':'0'});if(!c.vpn)tr.addEventListener")
    replace("tr.setAttribute('data-mac',c.mac);tr.classList", "tr.setAttribute('data-mac',c.mac);if(c.connection)tr.setAttribute('data-access',c.connection.kind);tr.classList")
    replace("tr.setAttribute('aria-label',_('Open details of %s').format(c.name));", "tr.setAttribute('aria-label',c.vpn?c.name:_('Open details of %s').format(c.name));")
    replace("var speed=c.speed?fmt.phyRate(c.speed.mbps*1000):fmt.DASH;var link=E(",
            """if(c.vpn) {
    return [E('td',{'class':'vt-td-name','data-title':_('Device')},[document.createTextNode(c.name)]),
        E('td',{'class':'vt-td-link','data-title':_('Link','vantage')},[document.createTextNode(c.connection.link)]),
        E('td',{'class':'vt-td-net','data-title':switchWord('接入方式','Access')},['VPN']),
        E('td',{'class':'vt-td-live','data-title':_('Live')},[fmt.DASH]),
        E('td',{'class':'vt-td-seen','data-title':_('Last heard')},[switchWord('已连接','Connected')])];
}
var speed=c.speed?fmt.phyRate(c.speed.mbps*1000):fmt.DASH;var link=E(""")
    replace("]);link.setAttribute('title',(c.shared?", """]);
if(c.connection) {
    dom.content(link,[E('div',{'class':'vt-phy vt-tn'},[document.createTextNode(c.connection.link)]),
        c.connection.detail ? E('div',{'class':'vt-phy vt-phy-up vt-tn'},[document.createTextNode(c.connection.detail)]) : '']);
}
link.setAttribute('title',(c.shared?""")
    replace("'data-title':_('Network')},[E('div',{'class':'vt-net'},[E('span',{'class':'vt-net-ssid'},[c.network||c.bridge||fmt.DASH])])]",
            "'data-title':c.connection?switchWord('接入方式','Access'):_('Network')},[E('div',{'class':'vt-net'},[E('span',{'class':'vt-net-ssid'},[c.connection?homeAccessLabel(c.connection.kind):c.network||c.bridge||fmt.DASH])])]")
    replace("sourceText:function(c){switch(c.nameSource){", "sourceText:function(c){switch(c.nameSource){case'unifi':return 'UniFi';")
    return text


if __name__ == '__main__':
    source, dest = map(Path, sys.argv[1:])
    data = source.read_bytes()
    if sha256(data).hexdigest() != EXPECTED:
        raise ValueError('Unexpected Vantage dashboard build')
    dest.write_bytes(patch(data.decode('utf-8')).encode('utf-8'))
