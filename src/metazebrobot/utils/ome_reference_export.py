"""OME-TIFF helpers for curated genotype reference PNG generation."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from PIL import Image, ImageSequence


@dataclass(frozen=True)
class OMEChannel:
    """Metadata for one logical OME channel."""

    index: int
    channel_id: Optional[str] = None
    name: Optional[str] = None
    fluor: Optional[str] = None
    color_hex: Optional[str] = None
    excitation_wavelength: Optional[str] = None
    emission_wavelength: Optional[str] = None

    @property
    def label(self) -> str:
        """Human-readable channel label."""
        return self.name or self.fluor or f"Channel {self.index}"

    def as_dict(self) -> Dict[str, Any]:
        """Return a template-friendly channel dictionary."""
        return {
            "index": self.index,
            "channel_id": self.channel_id,
            "name": self.name,
            "fluor": self.fluor,
            "color_hex": self.color_hex,
            "excitation_wavelength": self.excitation_wavelength,
            "emission_wavelength": self.emission_wavelength,
            "label": self.label,
        }


def decode_ome_color(value: Optional[str]) -> Optional[str]:
    """Decode OME signed 32-bit RGBA color text to #RRGGBB."""
    if value is None:
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    unsigned = parsed & 0xFFFFFFFF
    red = (unsigned >> 24) & 0xFF
    green = (unsigned >> 16) & 0xFF
    blue = (unsigned >> 8) & 0xFF
    return f"#{red:02X}{green:02X}{blue:02X}"


def _find_ome_xml(image: Image.Image) -> str:
    """Extract embedded OME-XML from the TIFF ImageDescription tag."""
    tag_value = image.tag_v2.get(270)
    if isinstance(tag_value, bytes):
        tag_value = tag_value.decode("utf-8", errors="replace")
    if isinstance(tag_value, tuple):
        tag_value = tag_value[0] if tag_value else ""
    tag_value = str(tag_value or "")
    if "<OME" not in tag_value:
        raise ValueError("TIFF does not contain embedded OME-XML metadata.")
    return tag_value


def read_ome_tiff_metadata(path: Path) -> Dict[str, Any]:
    """Read OME channel/dimension metadata without loading full image data."""
    path = Path(path)
    with Image.open(path) as image:
        ome_xml = _find_ome_xml(image)

    root = ET.fromstring(ome_xml)
    namespace_match = re.match(r"\{(?P<namespace>[^}]+)\}", root.tag)
    namespace = {"ome": namespace_match.group("namespace")} if namespace_match else {}
    pixels = root.find(".//ome:Image/ome:Pixels", namespace) if namespace else root.find(".//Image/Pixels")
    if pixels is None:
        raise ValueError("OME metadata does not contain an Image/Pixels element.")

    channels = []
    channel_nodes = pixels.findall("ome:Channel", namespace) if namespace else pixels.findall("Channel")
    for index, channel in enumerate(channel_nodes):
        channels.append(
            OMEChannel(
                index=index,
                channel_id=channel.attrib.get("ID"),
                name=channel.attrib.get("Name"),
                fluor=channel.attrib.get("Fluor"),
                color_hex=decode_ome_color(channel.attrib.get("Color")),
                excitation_wavelength=channel.attrib.get("ExcitationWavelength"),
                emission_wavelength=channel.attrib.get("EmissionWavelength"),
            )
        )

    size_c = int(pixels.attrib.get("SizeC", len(channels) or 1))
    if not channels:
        channels = [OMEChannel(index=index) for index in range(size_c)]

    return {
        "ome_xml": ome_xml,
        "size_x": int(pixels.attrib.get("SizeX", 0)),
        "size_y": int(pixels.attrib.get("SizeY", 0)),
        "size_c": size_c,
        "size_z": int(pixels.attrib.get("SizeZ", 1)),
        "size_t": int(pixels.attrib.get("SizeT", 1)),
        "pixel_type": pixels.attrib.get("Type"),
        "dimension_order": pixels.attrib.get("DimensionOrder"),
        "channels": [channel.as_dict() for channel in channels],
    }


def _autoscale_uint8(plane: np.ndarray) -> np.ndarray:
    """Convert one grayscale plane to uint8 using robust percentile scaling."""
    values = np.asarray(plane, dtype=np.float32)
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return np.zeros(values.shape, dtype=np.uint8)

    low, high = np.percentile(finite, [0.5, 99.8])
    if high <= low:
        low = float(finite.min())
        high = float(finite.max())
    if high <= low:
        return np.zeros(values.shape, dtype=np.uint8)

    scaled = (values - low) / (high - low)
    return np.clip(scaled * 255.0, 0, 255).astype(np.uint8)


def _rgb_from_hex(color_hex: Optional[str]) -> np.ndarray:
    """Return RGB triplet from #RRGGBB with white fallback."""
    if not color_hex or not re.fullmatch(r"#[0-9A-Fa-f]{6}", color_hex):
        return np.array([255, 255, 255], dtype=np.float32)
    return np.array(
        [
            int(color_hex[1:3], 16),
            int(color_hex[3:5], 16),
            int(color_hex[5:7], 16),
        ],
        dtype=np.float32,
    )


def _colorize_plane(plane_uint8: np.ndarray, color_hex: Optional[str]) -> np.ndarray:
    """Apply one display color to a uint8 grayscale plane."""
    rgb = _rgb_from_hex(color_hex)
    scaled = plane_uint8.astype(np.float32)[:, :, None] / 255.0
    return np.clip(scaled * rgb[None, None, :], 0, 255).astype(np.uint8)


def _safe_filename_part(value: str, fallback: str = "image") -> str:
    """Return a filesystem-safe filename component."""
    cleaned = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_")
    return (cleaned[:80] or fallback).strip("._") or fallback


def _load_channel_planes(path: Path, expected_channels: int) -> List[np.ndarray]:
    """Load the first plane for each OME channel from a simple OME-TIFF."""
    with Image.open(path) as image:
        frames = [np.array(frame) for frame in ImageSequence.Iterator(image)]

    if not frames:
        raise ValueError("OME-TIFF does not contain any image planes.")

    first = frames[0]
    if len(frames) == 1 and first.ndim == 3 and first.shape[-1] >= expected_channels:
        return [first[:, :, index] for index in range(expected_channels)]

    if len(frames) < expected_channels:
        raise ValueError(
            f"OME-TIFF has {len(frames)} image plane(s), fewer than SizeC={expected_channels}."
        )
    return frames[:expected_channels]


def export_reference_pngs_from_ome_tiff(
    ome_path: Path,
    output_dir: Path,
    filename_prefix: str,
) -> List[Dict[str, Any]]:
    """Generate one composite PNG plus one PNG per channel from an OME-TIFF."""
    metadata = read_ome_tiff_metadata(ome_path)
    channels = metadata["channels"]
    planes = _load_channel_planes(ome_path, metadata["size_c"])
    if len(channels) < len(planes):
        channels = channels + [
            OMEChannel(index=index).as_dict()
            for index in range(len(channels), len(planes))
        ]

    output_dir.mkdir(parents=True, exist_ok=True)
    safe_prefix = _safe_filename_part(filename_prefix, fallback="ome_reference")

    rendered_channels = []
    results = []
    for channel, plane in zip(channels, planes):
        plane_uint8 = _autoscale_uint8(plane)
        rendered = _colorize_plane(plane_uint8, channel.get("color_hex"))
        rendered_channels.append(rendered.astype(np.uint16))

        channel_name = _safe_filename_part(channel.get("name") or channel.get("fluor") or "channel")
        filename = f"{safe_prefix}_channel{channel['index']}_{channel_name}.png"
        Image.fromarray(rendered).save(output_dir / filename)
        results.append({
            "display_role": "channel",
            "image_filename": filename,
            "channel": channel,
        })

    composite = np.clip(np.sum(rendered_channels, axis=0), 0, 255).astype(np.uint8)
    composite_filename = f"{safe_prefix}_composite.png"
    Image.fromarray(composite).save(output_dir / composite_filename)

    return [
        {
            "display_role": "composite",
            "image_filename": composite_filename,
            "channel": None,
        },
        *results,
    ]
