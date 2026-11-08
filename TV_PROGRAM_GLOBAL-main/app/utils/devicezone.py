"""Vremenska zona uredjaja (IANA naziv) ili None ako se ne moze pouzdano utvrditi.

Na Androidu se cita iz sistema (java.util.TimeZone). Ako naziv nije IANA zona
(npr. "GMT+01:00"), vraca se None i aplikacija ostaje na zoni stanice; zona se ne nagadja.
"""

import logging
import os

LOGGER = logging.getLogger(__name__)


def _android_zone_id():
    from jnius import autoclass

    return str(autoclass("java.util.TimeZone").getDefault().getID())


def _desktop_zone_id():
    name = os.environ.get("TZ")
    if name:
        return name.lstrip(":")
    try:
        with open("/etc/timezone", encoding="utf-8") as handle:
            return handle.read().strip() or None
    except OSError:
        return None


def detect_device_zone_name():
    from app.utils.android_insets import is_android

    try:
        name = _android_zone_id() if is_android() else _desktop_zone_id()
    except Exception as error:  # JNI greske ne smeju da sruse aplikaciju
        LOGGER.warning("Zona uredjaja nije procitana: %s", error)
        return None
    if not name:
        return None
    from zoneinfo import ZoneInfo

    try:
        ZoneInfo(name)
    except Exception:  # nepoznata zona ili nema tzdata
        LOGGER.warning("Zona uredjaja %r nije IANA zona koju aplikacija poznaje", name)
        return None
    return name
