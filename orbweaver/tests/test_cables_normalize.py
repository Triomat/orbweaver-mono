"""Tests for cable normalization helpers."""

from orbweaver.cables.normalize import (
    DEFAULT_INTERFACE_MAPPINGS,
    normalize_chassis_mac,
    normalize_hostname,
    normalize_interface_name,
)


def test_normalize_hostname_strips_domain() -> None:
    assert normalize_hostname("switch1.example.com") == "switch1"


def test_normalize_hostname_lowercases() -> None:
    assert normalize_hostname("SWITCH1") == "switch1"


def test_normalize_hostname_trims_whitespace() -> None:
    assert normalize_hostname("  switch1  ") == "switch1"


def test_normalize_mac_removes_separators() -> None:
    assert normalize_chassis_mac("aa:bb:cc:dd:ee:ff") == "aabbccddeeff"
    assert normalize_chassis_mac("AA-BB-CC-DD-EE-FF") == "aabbccddeeff"


def test_normalize_interface_cisco_gi_to_gigabit() -> None:
    assert normalize_interface_name("Gi0/1", "cisco", DEFAULT_INTERFACE_MAPPINGS) == (
        "GigabitEthernet0/1",
        False,
    )


def test_normalize_interface_cisco_eth_to_ethernet() -> None:
    assert normalize_interface_name("Eth1/1", "cisco", DEFAULT_INTERFACE_MAPPINGS) == (
        "Ethernet1/1",
        False,
    )


def test_normalize_interface_aruba_already_canonical() -> None:
    assert normalize_interface_name("1/1", "aruba", DEFAULT_INTERFACE_MAPPINGS) == (
        "1/1",
        True,
    )


def test_normalize_interface_unknown_vendor_returns_none() -> None:
    assert normalize_interface_name("Gi0/1", "juniper", DEFAULT_INTERFACE_MAPPINGS) == (
        None,
        False,
    )


def test_normalize_interface_reports_canonical_name() -> None:
    assert normalize_interface_name(
        "GigabitEthernet0/1",
        "cisco",
        DEFAULT_INTERFACE_MAPPINGS,
    ) == ("GigabitEthernet0/1", True)


def test_interface_mapping_cache_hits() -> None:
    normalize_interface_name.cache_clear()
    normalize_interface_name("Gi0/1", "cisco", DEFAULT_INTERFACE_MAPPINGS)
    first = normalize_interface_name.cache_info()
    normalize_interface_name("Gi0/1", "cisco", DEFAULT_INTERFACE_MAPPINGS)
    second = normalize_interface_name.cache_info()

    assert first.hits == 0
    assert second.hits == 1
