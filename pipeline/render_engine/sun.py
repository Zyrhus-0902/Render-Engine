"""Sun position (NOAA solar calculator) and conversion to model-space vectors."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo


def _julian_day(dt_utc: datetime) -> float:
    return dt_utc.timestamp() / 86400.0 + 2440587.5


def solar_position(lat_deg: float, lon_deg: float, when: datetime) -> tuple[float, float]:
    """Return (azimuth, elevation) in degrees. Azimuth is clockwise from true north.

    `when` must be timezone-aware. Accurate to well under 0.1 deg for
    architectural purposes (atmospheric refraction ignored).
    """
    if when.tzinfo is None:
        raise ValueError("solar_position needs a timezone-aware datetime")
    utc = when.astimezone(timezone.utc)
    jc = (_julian_day(utc) - 2451545.0) / 36525.0

    L = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360
    M = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    e = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    Mr = math.radians(M)
    C = (math.sin(Mr) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
         + math.sin(2 * Mr) * (0.019993 - 0.000101 * jc)
         + math.sin(3 * Mr) * 0.000289)
    omega = math.radians(125.04 - 1934.136 * jc)
    app_long = L + C - 0.00569 - 0.00478 * math.sin(omega)
    mean_obliq = 23 + (26 + (21.448 - jc * (46.815 + jc * (0.00059 - jc * 0.001813))) / 60) / 60
    obliq = math.radians(mean_obliq + 0.00256 * math.cos(omega))
    decl = math.asin(math.sin(obliq) * math.sin(math.radians(app_long)))

    y = math.tan(obliq / 2) ** 2
    Lr = math.radians(L)
    eq_time = 4 * math.degrees(
        y * math.sin(2 * Lr) - 2 * e * math.sin(Mr) + 4 * e * y * math.sin(Mr) * math.cos(2 * Lr)
        - 0.5 * y * y * math.sin(4 * Lr) - 1.25 * e * e * math.sin(2 * Mr)
    )

    minutes = utc.hour * 60 + utc.minute + utc.second / 60
    tst = (minutes + eq_time + 4 * lon_deg) % 1440
    ha = math.radians(tst / 4 - 180)

    lat = math.radians(lat_deg)
    cos_zen = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(ha)
    zen = math.acos(max(-1.0, min(1.0, cos_zen)))
    elevation = 90 - math.degrees(zen)

    denom = math.cos(lat) * math.sin(zen)
    if abs(denom) < 1e-12:
        azimuth = 180.0 if lat_deg > math.degrees(decl) else 0.0
    else:
        c = (math.sin(lat) * math.cos(zen) - math.sin(decl)) / denom
        a = math.degrees(math.acos(max(-1.0, min(1.0, c))))
        azimuth = (a + 180) % 360 if ha > 0 else (540 - a) % 360
    return azimuth, elevation


def direction_from_az_el(azimuth_deg: float, elevation_deg: float, north_angle_deg: float = 0.0) -> tuple[float, float, float]:
    """Unit vector pointing *towards* the sun in model axes.

    Compass frame: north = +Y, east = +X. `north_angle_deg` is SketchUp's
    NorthAngle: how far true north is rotated clockwise (seen from above)
    away from the model's green (+Y) axis.
    """
    a = math.radians(azimuth_deg + north_angle_deg)
    el = math.radians(elevation_deg)
    return (math.sin(a) * math.cos(el), math.cos(a) * math.cos(el), math.sin(el))


def az_el_from_direction(v: tuple[float, float, float]) -> tuple[float, float]:
    """Inverse of direction_from_az_el with north_angle 0 (model-axes azimuth)."""
    x, y, z = v
    n = math.sqrt(x * x + y * y + z * z)
    az = math.degrees(math.atan2(x, y)) % 360
    el = math.degrees(math.asin(z / n))
    return az, el


def resolve_sun(sun_cfg: dict[str, Any], site: dict[str, Any], sketchup_shadow: dict[str, Any] | None) -> dict[str, Any]:
    """Resolve the style's sun settings to a model-space direction.

    Modes:
      fixed    - azimuth/elevation relative to true north (same light on every project)
      solar    - real sun for the site's location, date and time
      sketchup - exactly the sun direction set in SketchUp's Shadows panel
    """
    mode = sun_cfg.get("mode", "fixed")
    north = float(site.get("north_angle_deg", 0.0))

    if mode == "sketchup":
        if not sketchup_shadow or not sketchup_shadow.get("sun_direction"):
            raise ValueError("sun mode 'sketchup' needs shadow_info.sun_direction in scenes.json")
        d = tuple(float(c) for c in sketchup_shadow["sun_direction"])
        n = math.sqrt(sum(c * c for c in d))
        direction = (d[0] / n, d[1] / n, d[2] / n)
        source = "sketchup shadow settings"
    elif mode == "solar":
        tz = ZoneInfo(site["timezone"])
        when = datetime.fromisoformat(f"{sun_cfg['date']}T{sun_cfg['time']}").replace(tzinfo=tz)
        az, el = solar_position(float(site["latitude"]), float(site["longitude"]), when)
        direction = direction_from_az_el(az, el, north)
        source = f"solar {when.isoformat()} az={az:.1f} el={el:.1f}"
    elif mode == "fixed":
        direction = direction_from_az_el(float(sun_cfg["azimuth_deg"]), float(sun_cfg["elevation_deg"]), north)
        source = f"fixed az={sun_cfg['azimuth_deg']} el={sun_cfg['elevation_deg']}"
    else:
        raise ValueError(f"unknown sun mode '{mode}'")

    model_az, elevation = az_el_from_direction(direction)
    return {
        "direction": [round(c, 6) for c in direction],
        "model_azimuth_deg": round(model_az, 4),
        "elevation_deg": round(elevation, 4),
        "strength": float(sun_cfg.get("strength", 4.0)),
        "angle_deg": float(sun_cfg.get("angle_deg", 0.53)),
        "color": sun_cfg.get("color", "#FFFFFF"),
        "source": source,
    }
