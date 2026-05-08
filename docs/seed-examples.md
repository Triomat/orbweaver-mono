# Seed API Examples

The examples below are valid YAML payloads for `POST /api/v1/seed`.

## Example 1: Bare Device with Interfaces

```yaml
sites:
  - name: DC1
    slug: dc1

manufacturers:
  - name: Cisco
    slug: cisco

device_types:
  - manufacturer: Cisco
    model: C9300-48P
    slug: c9300-48p

device_roles:
  - name: Access
    slug: access

devices:
  - name: sw1-dc1
    manufacturer: Cisco
    device_type: C9300-48P
    role: Access
    site: DC1
    interfaces:
      - name: GigabitEthernet1/0/1
        description: User port 1
      - name: GigabitEthernet1/0/48
        description: Uplink to distribution
        mac_address: 00:11:22:33:44:55
```

## Example 2: Access VLAN Assignment

```yaml
sites:
  - name: DC1
    slug: dc1

manufacturers:
  - name: Cisco
    slug: cisco

device_types:
  - manufacturer: Cisco
    model: C9300-48P
    slug: c9300-48p

device_roles:
  - name: Access
    slug: access

vlans:
  - vid: 100
    name: Users
    site: DC1

devices:
  - name: sw2-dc1
    manufacturer: Cisco
    device_type: C9300-48P
    role: Access
    site: DC1
    interfaces:
      - name: GigabitEthernet1/0/10
        description: User access port
        mode: access
        access_vlan: 100
```

## Example 3: Tagged VLAN Assignment

```yaml
sites:
  - name: DC1
    slug: dc1

manufacturers:
  - name: Cisco
    slug: cisco

device_types:
  - manufacturer: Cisco
    model: C9300-48P
    slug: c9300-48p

device_roles:
  - name: Access
    slug: access

vlans:
  - vid: 10
    name: Infra
    site: DC1
  - vid: 20
    name: Voice
    site: DC1

devices:
  - name: sw3-dc1
    manufacturer: Cisco
    device_type: C9300-48P
    role: Access
    site: DC1
    interfaces:
      - name: GigabitEthernet1/0/47
        description: Trunk uplink
        mode: tagged
        tagged_vlans: [10, 20]
```

## Example 4: Top-Level VLANs with Device References

```yaml
sites:
  - name: DC1
    slug: dc1
  - name: DC2
    slug: dc2

manufacturers:
  - name: Cisco
    slug: cisco

device_types:
  - manufacturer: Cisco
    model: C9300-48P
    slug: c9300-48p

device_roles:
  - name: Access
    slug: access

vlans:
  - vid: 100
    name: Users-DC1
    site: DC1
  - vid: 100
    name: Users-DC2
    site: DC2
  - vid: 999
    name: Global-Mgmt

devices:
  - name: sw4-dc1
    manufacturer: Cisco
    device_type: C9300-48P
    role: Access
    site: DC1
    interfaces:
      - name: GigabitEthernet1/0/24
        mode: access
        access_vlan: 100
      - name: GigabitEthernet1/0/48
        mode: tagged
        tagged_vlans: [100, 999]
```
