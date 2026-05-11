# orb-discovery

Orb discovery backends collection

- [device-discovery](./device-discovery/README.md) - Device Discovery Backend that uses [NAPALM](https://github.com/napalm-automation/napalm) Drivers.
- [network-discovery](./network-discovery/README.md) - Network Discovery Backend which is a wrapper over [NMAP](https://nmap.org/) scanner.
- [worker](./worker/README.md) - A Worker Backend that allows to run custom implementation as part of Orb Agent.
- [snmp-discover](./snmp-discovery/README.md) - Device discovery that uses SNMP

## Orbweaver Extensions

This repository also includes orbweaver extensions that layer on top of upstream device discovery:

- Vendor-aware collectors for Cisco IOS/IOS-XE and Aruba AOS-CX.
- Review workflow for device and cable approval before ingestion.
- LLDP cable resolution and NetBox ingestion with idempotent create-or-skip behavior.
- Cable observability endpoints for summary and machine-readable skip reasons.

### LLDP Cable Discovery

Cable discovery resolves LLDP neighbors into cable candidates, classifies confidence (`confirmed`, `partial`, `unresolvable`), and writes only safe candidates to NetBox.

- Feature flag: `ORBWEAVER_CABLES_ENABLED`
- Policy override: `cables_enabled` in defaults or per scope entry

Example policy snippet:

```yaml
policies:
	dc1-access:
		config:
			defaults:
				site: "DC1"
				role: "access-switch"
				cables_enabled: true
		scope:
			- hostname: 192.0.2.10
				username: admin
				password: secret
				collector: cisco_ios
```

Additional documentation:

- [Cable Resolution Guide](docs/cable-resolution.md)
- [Cable Discovery Examples](docs/cable-examples.md)