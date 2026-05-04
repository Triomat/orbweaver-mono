from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator


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


class SeedData(BaseModel):
    tenant: SeedTenant | None = None
    sites: list[SeedSite] = Field(default_factory=list)
    racks: list[SeedRack] = Field(default_factory=list)
    manufacturers: list[SeedManufacturer] = Field(default_factory=list)
    device_types: list[SeedDeviceType] = Field(default_factory=list)
    device_roles: list[SeedDeviceRole] = Field(default_factory=list)
    platforms: list[SeedPlatform] = Field(default_factory=list)
    devices: list[SeedDevice] = Field(default_factory=list)

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
