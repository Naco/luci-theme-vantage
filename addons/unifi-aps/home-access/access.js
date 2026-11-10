'use strict';
'require baseclass';

function list(value) {
	return Array.isArray(value) ? value : [];
}

function macKey(value) {
	return typeof value === 'string' && /^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$/i.test(value) ? value.toLowerCase() : '';
}

return baseclass.extend({
	kinds: [ 'wired', 'wifi', 'vpn', 'unknown' ],

	label: function(kind, word) {
		switch (kind) {
		case 'wired': return word('有线', 'Wired');
		case 'wifi': return 'Wi-Fi';
		case 'vpn': return 'VPN';
		default: return word('待确认', 'Unconfirmed');
		}
	},

	prepare: function(fdb, snapshot, unifi, hints, topology) {
		topology = topology || {};
		var bridge = topology.lan_bridge || 'br-lan';
		var ports = snapshot?.state === 'ok' ? snapshot.clients || {} : {};
		var bridgePorts = new Map(), portClients = new Map(), byIp = new Map();
		list(fdb).forEach(function(row) {
			var mac = macKey(row?.mac);
			if (!mac || row.bridge !== bridge || !/^(?:eth|lan)\d+$/.test(row.port)) return;
			if (!portClients.has(row.port)) portClients.set(row.port, new Set());
			portClients.get(row.port).add(mac);
			if (!bridgePorts.has(mac)) bridgePorts.set(mac, row.port);
			else if (bridgePorts.get(mac) !== row.port) bridgePorts.set(mac, null);
		});
		var switchClients = new Map();
		Object.entries(ports).forEach(function(pair) {
			if (!switchClients.has(pair[1])) switchClients.set(pair[1], new Set());
			switchClients.get(pair[1]).add(pair[0]);
		});
		Object.entries(hints || {}).forEach(function(pair) {
			var mac = macKey(pair[0]);
			if (!mac) return;
			list(pair[1]?.ipaddrs).forEach(function(ip) {
				if (!byIp.has(ip)) byIp.set(ip, mac);
				else if (byIp.get(ip) !== mac) byIp.set(ip, null);
			});
		});
		var apByName = new Map(), apMacs = new Set(), apPorts = new Set();
		var aps = list(unifi?.aps).map(function(ap) {
			var mac = byIp.get(ap.ip), port = mac && ports[mac];
			if (mac) apMacs.add(mac);
			if (port) apPorts.add(port);
			var entry = { name: ap.name, ip: ap.ip, model: ap.model, port: port || '' };
			apByName.set(ap.name, apByName.has(ap.name) ? null : entry);
			return entry;
		});
		return { aps: aps, clients: unifi?.clients || {}, ports: ports, bridgePorts: bridgePorts,
			portClients: portClients, switchClients: switchClients, apByName: apByName, apMacs: apMacs,
			apPorts: apPorts, complete: aps.length > 0 && aps.every(function(ap) { return !!ap.port; }),
			switchUplink: topology.switch_uplink || '', switchLabel: topology.switch_label || 'Switch',
			lanInterface: topology.lan_interface || 'lan' };
	},

	classify: function(client, context, word) {
		if (client.vpn) return { kind: 'vpn', link: 'OpenVPN · ' + client.ip };
		if (client.ifname && !client.gone) return { kind: 'wifi', link: client.ssid || client.ifname };
		var mac = macKey(client.mac), routerPort = context.bridgePorts.get(mac);
		// A router port outside the switch uplink takes priority over learned switch entries.
		var port = routerPort && context.switchUplink && routerPort !== context.switchUplink ? '' : context.ports[mac];
		var lastAp = context.clients[mac]?.ap || client.unifiAp;
		var ap = context.apByName.get(lastAp);
		var switchLink = port ? context.switchLabel + ' · ' + port : '';
		var recent = lastAp ? word('最近 AP · ', 'Last AP · ') + lastAp : '';
		if (ap && port && ap.port === port && !context.apMacs.has(mac))
			return { kind: 'wifi', link: recent, detail: switchLink };
		if (port && (context.apMacs.has(mac) || (context.complete && !lastAp &&
		    !context.apPorts.has(port) && context.switchClients.get(port)?.size === 1)))
			return { kind: 'wired', link: switchLink };
		if (!port && routerPort && routerPort !== context.switchUplink && context.portClients.get(routerPort)?.size === 1)
			return { kind: 'wired', link: word('路由器直连 · ', 'Router port · ') + routerPort, detail: recent };
		return { kind: 'unknown', link: switchLink || routerPort || '—', detail: recent };
	},

	vpnRows: function(reply) {
		return reply?.state === 'ok' ? list(reply.clients).map(function(client) {
			return { vpn: true, ip: client.ip, name: client.name || client.ip, mac: 'vpn:' + client.ip, ips: [ client.ip ] };
		}) : [];
	}
});
