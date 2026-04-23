from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


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
