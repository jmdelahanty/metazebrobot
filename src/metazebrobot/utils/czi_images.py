"""Zeiss CZI screening images (docs/czi_screening_images_design.md).

Reads the acquisition settings ZEN's OME-TIFF export drops (filter cube,
exposure, lamp, binning, zoom) and converts a CZI to an OME-TIFF so the
existing preview and browser viewer can show it.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

CZI_SUFFIX = ".czi"


def is_czi(path: Path) -> bool:
    return Path(path).name.lower().endswith(CZI_SUFFIX)


def _text(node: Optional[ET.Element], path: str) -> Optional[str]:
    found = node.find(path) if node is not None else None
    text = (found.text or "").strip() if found is not None else ""
    return text or None


def _number(text: Optional[str]) -> Optional[float]:
    try:
        return float((text or "").replace("%", "").strip())
    except ValueError:
        return None


def _argb_to_hex(value: Optional[str]) -> Optional[str]:
    """'#FFFF0900' (ZEN's #AARRGGBB) -> '#FF0900'."""
    text = (value or "").strip().lstrip("#")
    if len(text) == 8:
        text = text[2:]
    return f"#{text.upper()}" if len(text) == 6 else None


def parse_metadata(xml_text: str) -> Dict[str, Any]:
    """Channels, size and acquisition settings from a CZI's metadata XML."""
    root = ET.fromstring(xml_text)
    meta = root.find("Metadata")
    image = meta.find("Information/Image") if meta is not None else None
    lamps = {ls.get("Id"): ls.get("Name") for ls in root.iter("LightSource")
             if ls.get("Name") and ls.get("Id")}
    channels: List[Dict[str, Any]] = []
    acquisition_channels: List[Dict[str, Any]] = []
    for channel in (image.findall("Dimensions/Channels/Channel") if image is not None else []):
        exposure_ns = _number(_text(channel, "ExposureTime"))
        setting = channel.find("LightSourcesSettings/LightSourceSettings")
        lamp_ref = setting.find("LightSource") if setting is not None else None
        channels.append({
            "name": channel.get("Name"),
            "fluor": _text(channel, "Fluor"),
            "color_hex": _argb_to_hex(_text(channel, "Color")),
            "excitation_wavelength": _text(channel, "ExcitationWavelength"),
            "emission_wavelength": _text(channel, "EmissionWavelength"),
        })
        acquisition_channels.append({
            "name": channel.get("Name"),
            "reflector": _text(channel, "Reflector"),
            "exposure_ms": round(exposure_ns / 1e6, 3) if exposure_ns is not None else None,
            "lamp": lamps.get(lamp_ref.get("Id")) if lamp_ref is not None else None,
            "lamp_intensity_pct": _number(_text(setting, "Intensity")),
            "binning": (_text(channel, "DetectorSettings/Binning") or "").replace(",", "x") or None,
        })
    pixel_m = _number(_text(meta, "Scaling/Items/Distance[@Id='X']/Value"))
    acquisition = {
        "acquired_at": _text(image, "AcquisitionDateAndTime"),
        "camera": _text(meta, "Scaling/AutoScaling/CameraName"),
        "objective": _text(meta, "Scaling/AutoScaling/ObjectiveName"),
        "zoom": _number(_text(image, "MicroscopeSettings/ZoomSettings/Magnification")),
        "pixel_size_um": round(pixel_m * 1e6, 4) if pixel_m else None,
        "channels": acquisition_channels,
    }
    return {
        "channels": channels,
        "size_x": int(_text(image, "SizeX")) if _text(image, "SizeX") else None,
        "size_y": int(_text(image, "SizeY")) if _text(image, "SizeY") else None,
        "acquisition": acquisition,
    }


def read_metadata(path: Path) -> Dict[str, Any]:
    import czifile

    with czifile.CziFile(str(path)) as czi:
        return parse_metadata(czi.metadata())


def _cyx(czi) -> np.ndarray:
    """The first scene as (C, Y, X): first plane of any other axis."""
    image = czi.scenes[0]
    data = image.asarray()
    dims = list(image.dims)
    for axis in [d for d in dims if d not in ("C", "S", "Y", "X")]:
        data = np.take(data, 0, axis=dims.index(axis))
        dims.remove(axis)
    if "S" in dims:  # colour camera samples: treat as channels when there are none
        if "C" in dims:
            data = np.take(data, 0, axis=dims.index("S"))
            dims.remove("S")
        else:
            dims[dims.index("S")] = "C"
    if "C" not in dims:
        data = data[np.newaxis]
        dims.insert(0, "C")
    return np.transpose(data, [dims.index("C"), dims.index("Y"), dims.index("X")])


def _ome_color(color_hex: Optional[str]) -> int:
    """'#FF0900' -> OME's signed 32-bit RGBA int (white if unknown)."""
    rgb = int((color_hex or "#FFFFFF").lstrip("#"), 16)
    value = (rgb << 8) | 0xFF
    return value - (1 << 32) if value >= (1 << 31) else value


def to_ome_tiff(source: Path, target: Path) -> Path:
    """Write ``source`` (a CZI) as an OME-TIFF with its channel names, colours and pixel size."""
    import czifile
    import tifffile

    with czifile.CziFile(str(source)) as czi:
        meta = parse_metadata(czi.metadata())
        data = _cyx(czi)
    channels = meta["channels"] or [{}]
    while len(channels) < data.shape[0]:
        channels.append({})
    names = [c.get("name") or c.get("fluor") or f"Channel {i}" for i, c in enumerate(channels)]
    ome: Dict[str, Any] = {
        "axes": "CYX",
        "Channel": {
            "Name": names[:data.shape[0]],
            "Fluor": [c.get("fluor") or "" for c in channels][:data.shape[0]],
            "Color": [_ome_color(c.get("color_hex")) for c in channels][:data.shape[0]],
        },
    }
    pixel = meta["acquisition"].get("pixel_size_um")
    if pixel:
        ome.update(PhysicalSizeX=pixel, PhysicalSizeY=pixel)  # µm is OME's default unit
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".partial")
    tifffile.imwrite(partial, data, ome=True, metadata=ome, photometric="minisblack")
    partial.replace(target)
    return target


def summary(acquisition: Optional[Dict[str, Any]]) -> List[str]:
    """One short line per channel, e.g. '63 HE mRFP · 150 ms · lamp 99% · bin 1x1'."""
    if not acquisition:
        return []
    zoom = acquisition.get("zoom")
    lines = []
    for channel in acquisition.get("channels") or []:
        parts = [channel.get("reflector") or "cube not recorded"]
        if channel.get("exposure_ms") is not None:
            parts.append(f"{channel['exposure_ms']:g} ms")
        if channel.get("lamp_intensity_pct") is not None:
            parts.append(f"lamp {channel['lamp_intensity_pct']:g}%")
        if channel.get("binning"):
            parts.append(f"bin {channel['binning']}")
        if zoom:
            parts.append(f"zoom {zoom:.2f}×")
        lines.append(" · ".join(parts))
    return lines
