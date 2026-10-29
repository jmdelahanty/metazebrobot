"""CZI screening images (docs/czi_screening_images_design.md)."""

import uuid

import numpy as np
import pytest
import tifffile

from metazebrobot.data.data_manager import data_manager
from metazebrobot.data.image_links import well_from_filename
from metazebrobot.models.fish_dish import FishDish
from metazebrobot.utils import czi_images
from metazebrobot.utils.ome_reference_export import read_ome_tiff_metadata

# The structure ZEN writes (2026-10-29 snaps), trimmed to the fields read.
CZI_XML = """<ImageDocument><Metadata>
  <Information>
    <Image>
      <SizeX>8</SizeX><SizeY>6</SizeY>
      <AcquisitionDateAndTime>2026-10-29T16:40:13.7898741Z</AcquisitionDateAndTime>
      <Dimensions><Channels>
        <Channel Id="Channel:0" Name="mCher">
          <Color>#FFFF0900</Color><Fluor>mCherry</Fluor>
          <ExcitationWavelength>587</ExcitationWavelength><EmissionWavelength>610</EmissionWavelength>
          <ExposureTime>150000000</ExposureTime>
          <Reflector>63 HE mRFP</Reflector>
          <DetectorSettings><Binning>1,1</Binning></DetectorSettings>
          <LightSourcesSettings><LightSourceSettings>
            <LightSource Id="LightSource:1" /><Intensity>99.00 %</Intensity>
          </LightSourceSettings></LightSourcesSettings>
        </Channel>
      </Channels></Dimensions>
      <MicroscopeSettings><ZoomSettings><Magnification>4.5099999231952</Magnification></ZoomSettings></MicroscopeSettings>
    </Image>
    <Instrument><LightSources><LightSource Id="LightSource:1" Name="X-Cite Xylis II Lamp" /></LightSources></Instrument>
  </Information>
  <Scaling>
    <Items><Distance Id="X"><Value>7.649667536037957E-07</Value></Distance></Items>
    <AutoScaling><CameraName>Axiocam 305</CameraName><ObjectiveName>PlanNeoFluar Z 1.0x</ObjectiveName></AutoScaling>
  </Scaling>
</Metadata></ImageDocument>"""

PIXELS = (np.arange(48, dtype=np.uint16).reshape(6, 8) * 50)


class _Scene:
    dims = ("Y", "X")

    def asarray(self):
        return PIXELS


class _FakeCzi:
    """Stands in for czifile.CziFile: real CZIs are lab data and not committed."""

    def __init__(self, path):
        self.path = path
        self.scenes = [_Scene()]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def metadata(self):
        return CZI_XML


@pytest.fixture()
def fake_czifile(monkeypatch):
    import czifile
    monkeypatch.setattr(czifile, "CziFile", _FakeCzi)


def test_metadata_has_what_the_ome_tiff_export_drops():
    meta = czi_images.parse_metadata(CZI_XML)
    assert meta["channels"] == [{"name": "mCher", "fluor": "mCherry", "color_hex": "#FF0900",
                                 "excitation_wavelength": "587", "emission_wavelength": "610"}]
    assert (meta["size_x"], meta["size_y"]) == (8, 6)
    acq = meta["acquisition"]
    assert acq["channels"] == [{"name": "mCher", "reflector": "63 HE mRFP", "exposure_ms": 150.0,
                                "lamp": "X-Cite Xylis II Lamp", "lamp_intensity_pct": 99.0,
                                "binning": "1x1"}]
    assert acq["camera"] == "Axiocam 305" and acq["pixel_size_um"] == 0.765
    assert czi_images.summary(acq) == ["63 HE mRFP · 150 ms · lamp 99% · bin 1x1 · zoom 4.51×"]


def test_conversion_keeps_channel_colour_and_pixel_size(fake_czifile, tmp_path):
    out = czi_images.to_ome_tiff(tmp_path / "x.czi", tmp_path / "out" / "x.ome.tiff")
    assert np.array_equal(tifffile.imread(out), PIXELS)
    channel = read_ome_tiff_metadata(out)["channels"][0]
    assert (channel["name"], channel["fluor"], channel["color_hex"]) == ("mCher", "mCherry", "#FF0900")
    assert 'PhysicalSizeX="0.765"' in read_ome_tiff_metadata(out)["ome_xml"]


def test_czi_well_from_filename():
    assert well_from_filename("19445_2_A1.czi") == "A1"
    assert well_from_filename("Snap-471.czi") is None


def test_czi_links_with_settings_previews_and_opens_in_the_viewer(client, tmp_path, fake_czifile):
    dish = FishDish.create_new(
        cross_id=f"CROSS_{uuid.uuid4().hex[:6]}", dish_number=1, genotype="Tg(gfap:PMCA2-mCherry-zf)",
        responsible="t", fish_count=10, dof="20261023", container_type="petri_dish",
    ).model_dump(mode="json", exclude_none=True)
    data_manager.save_fish_dish(dish)
    dish_id = dish["dish_id"]
    root = tmp_path / "staging"
    (root / dish_id).mkdir(parents=True)
    (root / dish_id / "Snap-471.czi").write_bytes(b"ZISRAWFILE fake czi bytes")
    client.app.state.ome_staging_root = root
    client.app.state.image_cache_dir = tmp_path / "cache"
    client.app.state.image_cache_dir.mkdir()

    assert "Snap-471.czi" in client.get("/image-links/import", params={"folder": dish_id}).text
    client.post("/image-links/import", data={"dish_id": dish_id, "kind": "screening",
                                              "include_1": "on", "rel_1": f"{dish_id}/Snap-471.czi"})
    item = client.get(f"/dishes/{dish_id}/image-links").json()["items"][0]
    assert item["acquisition"]["channels"][0]["reflector"] == "63 HE mRFP"
    assert item["channels"][0]["color_hex"] == "#FF0900"
    assert "63 HE mRFP · 150 ms · lamp 99%" in client.get(f"/dishes/{dish_id}/image-links/gallery").text

    ome = client.get(f"/image-links/{item['id']}/image.ome.tiff")
    assert ome.status_code == 200 and ome.headers["content-type"] == "image/tiff"
    assert ome.content[:4] in (b"II*\x00", b"MM\x00*", b"II+\x00")
    preview = client.get(f"/image-links/{item['id']}/preview.png")
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/png"
    original = client.get(f"/image-links/{item['id']}/file")
    assert original.content == b"ZISRAWFILE fake czi bytes"
