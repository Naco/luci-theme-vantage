'use strict';
'require baseclass';
'require rpc';
'require home-network.access as access';

var readSwitch = rpc.declare({ object: 'luci.vantage_switch', method: 'snapshot' });
var readInternet = rpc.declare({ object: 'luci.vantage_internet', method: 'counters' });
var readAps = rpc.declare({ object: 'luci.unifi_aps', method: 'list' });
var readHosts = rpc.declare({ object: 'luci-rpc', method: 'getHostHints' });
var readAliases = rpc.declare({ object: 'uci', method: 'get', params: [ 'config', 'type' ], expect: { values: {} } });
var readWired = rpc.declare({ object: 'luci.vantage', method: 'wired' });
var readVpn = rpc.declare({ object: 'luci.home_access', method: 'vpn' });

var CSS = [
	'#home-network-overview .hn-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,138px),1fr));gap:8px}',
	'#home-network-overview .hn-card{border:1px solid currentColor;border-color:color-mix(in srgb,currentColor 18%,transparent);border-radius:5px;padding:7px 9px;min-width:0;overflow-wrap:anywhere}',
	'#home-network-overview .hn-off{opacity:.65}',
	'#home-network-overview .hn-port-title{display:flex;justify-content:space-between;gap:6px}',
	'#home-network-overview .hn-ports>summary{cursor:pointer;margin-bottom:8px}',
	'#home-network-overview .hn-rate{font-variant-numeric:tabular-nums;white-space:nowrap}',
	'#home-network-overview .hn-filters{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}',
	'#home-network-overview .hn-filters button[aria-pressed="true"]{font-weight:bold;text-decoration:underline}',
	'#home-network-overview .hn-list{max-height:21rem;overflow:auto}',
	'#home-network-overview .hn-list td{overflow-wrap:anywhere}',
	'#home-network-overview .hn-list th{position:sticky;top:0}'
].join('\n');

function zh(chinese, english) {
	return /^zh(?:[-_]|$)/i.test(document.documentElement.lang || '') ? chinese : english;
}

function text(value) {
	return document.createTextNode(String(value == null ? '' : value));
}

function rate(bytes) {
	if (bytes == null || !Number.isFinite(bytes)) return '—';
	var units = [ 'B/s', 'kB/s', 'MB/s', 'GB/s' ], i = 0;
	for (; bytes >= 1000 && i < units.length - 1; i++) bytes /= 1000;
	return Number(bytes.toPrecision(3)) + ' ' + units[i];
}

function addressKey(ip) {
	if (ip.indexOf(':') < 0) return ip;
	try {
		return new URL('http://[' + ip + ']/').hostname.slice(1, -1);
	}
	catch (e) {
		return ip;
	}
}

function aliasesByMac(sections) {
	var aliases = Object.create(null);
	Object.values(sections || {}).forEach(function(section) {
		if (!section || section['.type'] !== 'client' || typeof section.mac !== 'string' || typeof section.name !== 'string') return;
		var mac = section.mac.toLowerCase(), name = section.name.trim();
		if (name && /^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/.test(mac) && !aliases[mac]) aliases[mac] = name;
	});
	return aliases;
}

function clientName(mac, ip, hints, aliases, unifi) {
	return aliases[mac] || unifi[mac]?.name || hints?.name || ip;
}

function internetRows(previous, current, hints, aliases, unifi) {
	var elapsed = previous && current.at - previous.at;
	if (!current.hosts || !previous || !previous.hosts || !Number.isFinite(elapsed) || elapsed < 1 || elapsed > 60) return null;

	var byAddress = new Map(), rows = new Map();
	Object.keys(hints).forEach(function(mac) {
		var host = hints[mac];
		[].concat(host.ipaddrs || [], host.ip6addrs || []).forEach(function(ip) {
			var key = addressKey(ip);
			if (byAddress.has(key) && byAddress.get(key) !== mac) byAddress.set(key, null);
			else byAddress.set(key, mac);
		});
	});
	Object.keys(current.hosts).forEach(function(ip) {
		var now = current.hosts[ip], before = previous.hosts[ip] || {};
		var mac = byAddress.get(addressKey(ip));
		var id = mac || ip, row = rows.get(id);
		if (!row) {
			var key = mac && mac.toLowerCase();
			row = { name: clientName(key, ip, hints[mac], aliases, unifi),
				ip: ip, mac: key, rx: 0, tx: 0 };
			rows.set(id, row);
		}
		row.rx += Math.max(0, (now.rx || 0) - (before.rx || 0)) / elapsed;
		row.tx += Math.max(0, (now.tx || 0) - (before.tx || 0)) / elapsed;
	});
	return Array.from(rows.values()).sort(function(a, b) { return b.rx + b.tx - a.rx - a.tx; });
}

function switchPanel(snapshot, hints, expanded, switchLabel) {
	if (snapshot.state !== 'ok' || !Array.isArray(snapshot.ports))
		return E('p', {}, [ zh('交换机数据暂不可用。', 'Switch data is unavailable.') ]);
	var active = snapshot.ports.filter(function(p) { return p.up; }).length;
	var peers = new Map();
	Object.keys(snapshot.clients || {}).forEach(function(mac) {
		var port = snapshot.clients[mac], names = peers.get(port) || [];
		var hint = hints[mac] || hints[mac.toUpperCase()];
		names.push(hint?.name || hint?.ipaddrs?.[0] || mac);
		peers.set(port, names);
	});
	var panel = E('details', { 'class': 'hn-ports' }, [
		E('summary', {}, [ switchLabel + ' · ' + active + ' / ' + snapshot.ports.length + zh(' 个端口已连接', ' ports linked') ]),
		E('p', {}, [ zh('交换机视角：接收 / 发送，含局域网与上网流量。', 'From the switch: received / sent, including LAN and Internet traffic.') ]),
		E('div', { 'class': 'hn-grid' }, snapshot.ports.map(function(port) {
			var names = peers.get(port.name) || [];
			var description = port.neighbor || (names.length > 1 ? names.length + zh(' 台设备', ' devices') : names[0]);
			return E('div', { 'class': 'hn-card hn-switch-port' + (port.up ? '' : ' hn-off'), title: names.join(', ') }, [
				E('div', { 'class': 'hn-port-title' }, [
					E('strong', {}, [ text(port.name) ]),
					E('small', {}, [ port.up ? zh('已连接', 'Up') : zh('未连接', 'Down') ])
				]),
				E('div', {}, [ text(description || '—') ]),
				E('div', { 'class': 'hn-rate' }, [ zh('收 ', 'RX ') + rate(port.rate?.[0]) ]),
				E('div', { 'class': 'hn-rate' }, [ zh('发 ', 'TX ') + rate(port.rate?.[1]) ])
			]);
		}))
	]);
	panel.open = expanded;
	return panel;
}

function clientPanel(rows, kind, onSelect) {
	var panel = E('div'), devices = rows || [];
	panel.appendChild(E('div', { 'class': 'hn-filters' }, [ 'all' ].concat(access.kinds).map(function(value) {
		return E('button', { 'type': 'button', 'class': 'btn', 'aria-pressed': String(kind === value), 'click': function() {
			onSelect(value);
			panel.replaceWith(clientPanel(rows, value, onSelect));
		} }, [ value === 'all' ? zh('全部', 'All') : access.label(value, zh) ]);
	})));
	var shown = kind === 'all' ? devices : devices.filter(function(row) { return row.connection.kind === kind; });
	if (!shown.length) {
		panel.appendChild(E('p', {}, [ rows ? zh('此分类暂无客户端。', 'No clients in this category.') : zh('等待连续两次采样。', 'Waiting for two consecutive samples.') ]));
		return panel;
	}
	var headings = [ zh('设备', 'Device'), zh('链路', 'Link'), zh('接入方式', 'Access'), zh('下载', 'Download'), zh('上传', 'Upload') ];
	panel.appendChild(E('div', { 'class': 'hn-list' }, [
		E('table', { 'class': 'table' }, [
			E('thead', {}, [ E('tr', { 'class': 'tr table-titles' }, headings.map(function(title) {
				return E('th', { 'class': 'th', 'scope': 'col' }, [ title ]);
			})) ]),
			E('tbody', {}, shown.map(function(row) {
				return E('tr', { 'class': 'tr hn-client', 'data-access': row.connection.kind }, [
					E('td', { 'class': 'td' }, [ E('strong', {}, [ text(row.name) ]) ]
						.concat(row.name === row.ip ? [] : [ E('div', {}, [ text(row.ip) ]) ])),
					E('td', { 'class': 'td' }, [ text(row.connection.link) ].concat(row.connection.detail ? [
						E('div', {}, [ text(row.connection.detail) ])
					] : [])),
					E('td', { 'class': 'td' }, [ access.label(row.connection.kind, zh) ]),
					E('td', { 'class': 'td hn-rate' }, [ rate(row.rx) ]),
					E('td', { 'class': 'td hn-rate' }, [ rate(row.tx) ])
				]);
			}))
		])
	]));
	return panel;
}

function apPanel(data) {
	if (data.state !== 'ok' || !Array.isArray(data.aps) || !data.aps.length)
		return E('p', {}, [ zh('暂无可显示的 UniFi AP。', 'No UniFi access points to show.') ]);
	return E('div', { 'class': 'hn-grid' }, data.aps.map(function(ap) {
		return E('div', { 'class': 'hn-card hn-ap' }, [
			E('strong', {}, [ text(ap.name) ]),
			E('div', {}, [ text([ ap.model, ap.ip ].filter(Boolean).join(' · ')) ])
		]);
	}));
}

return baseclass.extend({
	title: zh('家庭网络监控', 'Home network monitoring'),

	load: function() {
		var now = Date.now(), self = this;
		if (!this.metadataAt || now - this.metadataAt >= 60000) {
			this.metadataAt = now;
			this.metadata = Promise.all([ L.resolveDefault(readHosts(), {}), L.resolveDefault(readAps(), {}),
				L.resolveDefault(readAliases('vantage', 'client'), {}).then(aliasesByMac) ]);
		}
		return Promise.all([ L.resolveDefault(readSwitch(), {}), L.resolveDefault(readInternet(), {}), this.metadata,
			L.resolveDefault(readWired(), {}), L.resolveDefault(readVpn(), {}) ])
			.then(function(data) {
				var counters = data[1], sw = data[0];
				var aps = data[2][1];
				var rows = internetRows(self.previous, counters, data[2][0], data[2][2],
					aps.state === 'ok' ? aps.clients || {} : {});
				var topology = data[4].topology || {}, fdb = data[3].hosts || [], hints = data[2][0];
				var context = access.prepare(fdb, sw, aps, hints, topology);
				rows = rows || [];
				var listed = new Set(rows.map(function(row) { return row.mac; }));
				fdb.forEach(function(host) {
					if (host.bridge !== (topology.lan_bridge || 'br-lan') || typeof host.mac !== 'string') return;
					var mac = host.mac.toLowerCase();
					if (listed.has(mac)) return;
					listed.add(mac);
					var hint = hints[mac] || hints[mac.toUpperCase()];
					var ip = hint?.ipaddrs?.[0] || hint?.ip6addrs?.[0] || mac;
					rows.push({ mac: mac, ip: ip, name: clientName(mac, ip, hint, data[2][2], context.clients) });
				});
				rows = rows.concat(access.vpnRows(data[4]));
				rows.forEach(function(row) { row.connection = access.classify(row, context, zh); });
				self.previous = counters.hosts && Number.isFinite(counters.at) ? counters : null;
				return { switch: sw, rows: rows, aps: aps, hints: hints, switchLabel: context.switchLabel };
			});
	},

	render: function(data) {
		var last = document.querySelector('#home-network-overview'), state = last?.querySelector('details');
		var priorList = last?.querySelector('.hn-list');
		var self = this, clients = clientPanel(data.rows, this.accessKind || 'all', function(kind) { self.accessKind = kind; });
		var list = clients.querySelector('.hn-list');
		if (priorList && list) {
			var scroll = priorList.scrollTop;
			requestAnimationFrame(function() { list.scrollTop = scroll; });
		}
		return E('div', { id: 'home-network-overview' }, [
			E('style', {}, [ text(CSS) ]),
			...(data.switch.state === 'ok' ? [ E('h4', {}, [ zh('交换机端口流量', 'Switch port traffic') ]),
				switchPanel(data.switch, data.hints, state ? state.open : true, data.switchLabel) ] : []),
			E('h4', {}, [ zh('客户端', 'Clients') ]),
			clients,
			E('h4', {}, [ 'UniFi AP' ]),
			apPanel(data.aps)
		]);
	}
});
