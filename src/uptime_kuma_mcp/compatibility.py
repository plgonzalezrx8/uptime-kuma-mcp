"""Exact compatibility policy for the initial release."""

SUPPORTED_KUMA_VERSION = "2.5.0"
KUMA_FIXTURE_IMAGE = (
    "louislam/uptime-kuma:2.5.0@"
    "sha256:a8610b3b4c38077922ba51b036691e06887d7cefd91fe620fd3d6d23d03dc240"
)

READ_ONLY_TOOLS = (
    "kuma_get_instance_info",
    "kuma_get_monitor_summary",
    "kuma_list_monitors",
    "kuma_get_monitor",
    "kuma_get_heartbeats",
    "kuma_get_chart_data",
    "kuma_list_tags",
    "kuma_list_maintenance",
    "kuma_list_status_pages",
    "kuma_list_notifications",
)


def is_supported(version: str | None) -> bool:
    """Return whether the connected Kuma version is exactly supported."""
    return version == SUPPORTED_KUMA_VERSION
