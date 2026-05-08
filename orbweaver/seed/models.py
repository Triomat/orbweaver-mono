from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class SeedTenant(BaseModel):
    name: str
    slug: str


class SeedSite(BaseModel):
    name: str
    slug: str
    description: str = ""
    status: str = "active"


class SeedRack(BaseModel):
    name: str
    site: str
    u_height: int = 42
    status: str = "active"


class SeedManufacturer(BaseModel):
    name: str
    slug: str


class SeedDeviceType(BaseModel):
    manufacturer: str
    model: str
    slug: str
    u_height: int = 1


class SeedDeviceRole(BaseModel):
    name: str
    slug: str
    color: str = "9e9e9e"

    @field_validator("color", mode="before")
    @classmethod
    def coerce_color_to_str(cls, v: object) -> str:
        return str(v)


class SeedPlatform(BaseModel):
    name: str
    slug: str
    manufacturer: str | None = None


class SeedVLAN(BaseModel):
    """VLAN seed specification."""
    vid: int = Field(..., ge=1, le=4094, description="VLAN ID")
    name: str = Field(..., min_length=1, max_length=64)
    site: str | None = Field(None, description="Site name; None = global VLAN")

    model_config = ConfigDict(extra="forbid")


class SeedInterface(BaseModel):
    """Interface seed specification under a device."""
    name: str = Field(..., min_length=1, max_length=64)
    description: str | None = Field(None, max_length=200)
    mac_address: str | None = Field(
        None,
        pattern=r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$",
        description="MAC address in EUI-48 format"
    )
    type: str = Field("1000base-t", description="Interface type")
    mode: str | None = Field(None, pattern="^(access|tagged|tagged-all)$")
    access_vlan: int | None = Field(None, ge=1, le=4094)
    tagged_vlans: list[int] | None = Field(None, description="VLAN IDs for tagged mode")

    @field_validator("tagged_vlans")
    @classmethod
    def validate_tagged_vlans(cls, v: list[int] | None) -> list[int] | None:
        """Ensure all VLANs are in valid range."""
        if v:
            for vlan_id in v:
                if not (1 <= vlan_id <= 4094):
                    raise ValueError(f"VLAN ID {vlan_id} out of range [1, 4094]")
        return v

    @model_validator(mode="after")
    def validate_vlan_mode_constraints(self) -> "SeedInterface":
        """Validate mode-specific VLAN constraints."""
        if self.mode == "tagged-all":
            # tagged-all does not use explicit VLAN lists
            self.access_vlan = None
            self.tagged_vlans = None
            return self

        if self.access_vlan is not None and self.tagged_vlans is not None:
            raise ValueError("Cannot specify both access_vlan and tagged_vlans")

        if self.mode == "access" and self.access_vlan is None:
            raise ValueError("mode 'access' requires access_vlan")

        if self.mode == "tagged" and not self.tagged_vlans:
            raise ValueError("mode 'tagged' requires tagged_vlans")

        return self

    model_config = ConfigDict(extra="forbid")


class SeedDevice(BaseModel):
    name: str
    device_type: str
    manufacturer: str
    role: str
    site: str
    rack: str | None = None
    position: int | None = None
    face: str | None = None
    airflow: str | None = None
    serial: str | None = None
    tenant: str | None = None
    platform: str | None = None
    status: str = "active"
    primary_ip4: str | None = None
    comments: str = ""
    tags: list[str] = Field(default_factory=list)
    parent_device: str | None = None
    parent_bay: str | None = None
    interfaces: list[SeedInterface] | None = Field(None, description="Interfaces to seed on this device")

    @field_validator("interfaces")
    @classmethod
    def validate_unique_interface_names(cls, v: list[SeedInterface] | None) -> list[SeedInterface] | None:
        """Ensure no duplicate interface names under same device."""
        if v:
            names = [iface.name for iface in v]
            if len(names) != len(set(names)):
                duplicates = [n for n in names if names.count(n) > 1]
                raise ValueError(
                    f"Duplicate interface names under same device: {duplicates}"
                )
        return v


class SeedData(BaseModel):
    tenant: SeedTenant | None = None
    sites: list[SeedSite] = Field(default_factory=list)
    racks: list[SeedRack] = Field(default_factory=list)
    manufacturers: list[SeedManufacturer] = Field(default_factory=list)
    device_types: list[SeedDeviceType] = Field(default_factory=list)
    device_roles: list[SeedDeviceRole] = Field(default_factory=list)
    platforms: list[SeedPlatform] = Field(default_factory=list)
    vlans: list[SeedVLAN] | None = Field(None, description="VLANs to seed")
    devices: list[SeedDevice] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_references(self) -> "SeedData":
        site_names = {site.name for site in self.sites}
        rack_keys = {(rack.site, rack.name) for rack in self.racks}
        manufacturer_names = {manufacturer.name for manufacturer in self.manufacturers}
        device_type_keys = {
            (device_type.manufacturer, device_type.model) for device_type in self.device_types
        }
        role_names = {role.name for role in self.device_roles}
        platform_names = {platform.name for platform in self.platforms}
        device_names = {device.name for device in self.devices}
        errors: list[str] = []

        for rack in self.racks:
            if rack.site not in site_names:
                errors.append(f"rack '{rack.name}' references unknown site '{rack.site}'")

        for device in self.devices:
            if device.site not in site_names:
                errors.append(f"device '{device.name}' references unknown site '{device.site}'")

            if device.rack and (device.site, device.rack) not in rack_keys:
                errors.append(
                    f"device '{device.name}' references unknown rack '{device.rack}' at site '{device.site}'"
                )

            if device.manufacturer not in manufacturer_names:
                errors.append(
                    f"device '{device.name}' references unknown manufacturer '{device.manufacturer}'"
                )

            if (device.manufacturer, device.device_type) not in device_type_keys:
                errors.append(
                    f"device '{device.name}' references unknown device type '{device.device_type}' for manufacturer '{device.manufacturer}'"
                )

            if device.role not in role_names:
                errors.append(f"device '{device.name}' references unknown role '{device.role}'")

            if device.platform and device.platform not in platform_names:
                errors.append(
                    f"device '{device.name}' references unknown platform '{device.platform}'"
                )

            if bool(device.parent_device) != bool(device.parent_bay):
                errors.append(
                    f"device '{device.name}' must define both parent_device and parent_bay together"
                )

            if device.parent_device and device.parent_device not in device_names:
                errors.append(
                    f"device '{device.name}' references unknown parent device '{device.parent_device}'"
                )

        if errors:
            raise ValueError("; ".join(errors))

        return self
