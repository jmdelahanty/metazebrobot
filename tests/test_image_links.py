"""Screening images linked by reference (docs/screening_images_design.md)."""

import uuid

import numpy as np
import pytest
from PIL import Image, TiffImagePlugin

from metazebrobot.data.image_links import well_from_filename
from metazebrobot.data.propagation import constructs_for
from metazebrobot.data.data_manager import data_manager
from metazebrobot.models.fish_dish import FishDish

OME_XML = """<?xml version="1.0" encoding="UTF-8"?>
<OME xmlns="http://www.openmicroscopy.org/Schemas/OME/2016-06">
  <Image ID="Image:0"><Pixels BigEndian="false" DimensionOrder="XYZTC" ID="Pixels:0"
      SizeC="1" SizeT="1" SizeX="8" SizeY="6" SizeZ="1" Type="uint16">
    <Channel Color="-16187137" Fluor="mCherry" ID="Channel:0:0" Name="mCher" SamplesPerPixel="1"/>
    <TiffData/></Pixels></Image></OME>"""


def _ome(path):
    info = TiffImagePlugin.ImageFileDirectory_v2()
    info[270] = OME_XML
    Image.fromarray(np.arange(48, dtype=np.uint16).reshape(6, 8) * 50).save(path, tiffinfo=info)


@pytest.mark.parametrize("name, well", [
    ("19327_6_pos1_A1-OME TIFF-Export-01.ome.tiff", "A1"),
    ("19372_6_pos1_A2-OME TIFF-Export-02.ome.tiff", "A2"),  # typo'd dish, well still found
    ("A3-OME TIFF-Export-03.ome.tiff", "A3"),
    ("B12-OME TIFF-Export-05.ome.tiff", "B12"),
    ("Snap-398-OME TIFF-Export-01.ome.tiff", None),
])
def test_well_from_filename(name, well):
    assert well_from_filename(name) == well


@pytest.fixture()
def plate_with_images(client, tmp_path):
    dish = FishDish.create_new(
        cross_id=f"CROSS_{uuid.uuid4().hex[:6]}", dish_number=1, genotype="Tg(gfap:PMCA2-mCherry-zf)",
        responsible="t", fish_count=0, dof="20261008", container_type="well_plate",
    ).model_dump(mode="json", exclude_none=True)
    data_manager.save_fish_dish(dish)
    plate = dish["dish_id"]
    client.post(f"/dishes/{plate}/plate/setup", data={"wells": 6})
    fish = {}
    for label, well in (("Z1", "A1"), ("Z2", "A2")):
        fid = client.post(f"/dishes/{plate}/fish", json={"subject_label": label}).json()["fish_id"]
        client.post(f"/fish/{fid}/assign", json={"unit_id": f"{plate}:{well}"})
        fish[label] = fid

    root = tmp_path / "staging"
    (root / plate).mkdir(parents=True)
    _ome(root / plate / f"{plate}_A1-OME TIFF-Export-01.ome.tiff")
    _ome(root / plate / "19372_6_pos1_A2-OME TIFF-Export-02.ome.tiff")
    _ome(root / plate / "Snap-1-OME TIFF-Export-03.ome.tiff")
    (root / "cross_folder").mkdir()
    _ome(root / "cross_folder" / "Snap-9-OME TIFF-Export-01.ome.tiff")
    client.app.state.ome_staging_root = root
    client.app.state.image_cache_dir = tmp_path / "cache"
    client.app.state.image_cache_dir.mkdir()
    return plate, fish


def test_scan_link_preview_and_galleries(client, plate_with_images):
    plate, fish = plate_with_images
    page = client.get("/image-links/import", params={"folder": plate})
    assert "Z1" in page.text and "Z2" in page.text and "dish only" in page.text

    form = {"dish_id": plate, "kind": "plate"}
    names = [f"{plate}_A1-OME TIFF-Export-01.ome.tiff", "19372_6_pos1_A2-OME TIFF-Export-02.ome.tiff",
             "Snap-1-OME TIFF-Export-03.ome.tiff"]
    fish_for = [fish["Z1"], fish["Z2"], None]
    for i, (name, fid) in enumerate(zip(names, fish_for), start=1):
        form[f"include_{i}"] = "on"
        form[f"rel_{i}"] = f"{plate}/{name}"
        if fid:
            form[f"fish_{i}"] = fid
    resp = client.post("/image-links/import", data=form, follow_redirects=False)
    assert resp.status_code == 303

    items = client.get(f"/dishes/{plate}/image-links").json()["items"]
    assert len(items) == 3
    a2 = next(i for i in items if i["well_label"] == "A2")
    assert a2["fish_id"] == fish["Z2"] and a2["channels"][0]["fluor"] == "mCherry"
    assert len(a2["sha256"]) == 64

    preview = client.get(f"/image-links/{a2['id']}/preview.png")
    assert preview.status_code == 200 and preview.headers["content-type"] == "image/png"
    original = client.get(f"/image-links/{a2['id']}/file", headers={"Range": "bytes=0-15"})
    assert original.status_code == 206 and len(original.content) == 16

    assert client.get(f"/fish/{fish['Z2']}/image-links").json()["items"][0]["id"] == a2["id"]
    assert "Z2" in client.get(f"/dishes/{plate}/image-links/gallery").text
    timeline = client.get(f"/fish/{fish['Z2']}/timeline").json()["entries"]
    assert any(e["kind"] == "imaged" and "well A2" in e["summary"] for e in timeline)

    again = client.get("/image-links/import", params={"folder": plate}).text
    assert again.count(">linked<") == 3  # re-scan marks them linked


def test_cross_folder_needs_a_dish_and_paths_cannot_escape(client, plate_with_images):
    plate, _ = plate_with_images
    page = client.get("/image-links/import", params={"folder": "cross_folder"})
    assert "No dish named cross_folder" in page.text
    page = client.get("/image-links/import", params={"folder": "cross_folder", "dish_id": plate})
    assert "dish only" in page.text
    escaped = client.get("/image-links/import", params={"folder": "../../etc"})
    assert "outside the screening staging root" in escaped.text


def test_viewer_is_served_and_gallery_links_to_it(client, plate_with_images):
    plate, fish = plate_with_images
    viewer = client.get("/viewer/")
    assert viewer.status_code == 200 and "/viewer/assets/" in viewer.text
    form = {"dish_id": plate, "kind": "plate", "include_1": "on",
            "rel_1": f"{plate}/{plate}_A1-OME TIFF-Export-01.ome.tiff", "fish_1": fish["Z1"]}
    client.post("/image-links/import", data=form)
    link_id = client.get(f"/dishes/{plate}/image-links").json()["items"][0]["id"]
    gallery = client.get(f"/dishes/{plate}/image-links/gallery").text
    assert f"/viewer/?image_url=http://testserver/image-links/{link_id}/image.ome.tiff" in gallery
    tiff = client.get(f"/image-links/{link_id}/image.ome.tiff", headers={"Range": "bytes=0-3"})
    assert tiff.status_code == 206 and tiff.headers["content-type"] == "image/tiff"


def test_mark_reference_shows_by_line_on_references_and_screening(client, plate_with_images):
    plate, fish = plate_with_images
    with data_manager.get_connection() as conn:  # the genotype's construct, parsed on save
        assert [c["line_key"] for c in constructs_for(conn, [plate])] == ["gfap-pmca2mcherryzf"]
    client.post("/image-links/import", data={
        "dish_id": plate, "kind": "plate", "include_1": "on",
        "rel_1": f"{plate}/{plate}_A1-OME TIFF-Export-01.ome.tiff", "fish_1": fish["Z1"]})
    link_id = client.get(f"/dishes/{plate}/image-links").json()["items"][0]["id"]

    resp = client.post(f"/image-links/{link_id}/reference",
                       data={"caption": "bright gfap+ positive", "return_to": f"/dishes/{plate}/fish/"},
                       follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == f"/dishes/{plate}/fish/"
    item = next(i for i in client.get(f"/dishes/{plate}/image-links").json()["items"] if i["id"] == link_id)
    assert item["is_reference"] == 1 and item["reference_caption"] == "bright gfap+ positive"

    refs = client.get("/references/?line=gfap-pmca2mcherryzf").text
    assert "bright gfap+ positive" in refs
    assert "bright gfap+ positive" not in client.get("/references/?line=elavl3-grabatp10").text
    assert "bright gfap+ positive" in client.get(f"/screening/{plate}/genotype-reference").text
    assert "★" in client.get(f"/dishes/{plate}/image-links/gallery").text

    client.post(f"/image-links/{link_id}/reference", data={"action": "unmark", "return_to": "//evil"})
    assert "bright gfap+ positive" not in client.get("/references/").text
    assert client.post("/image-links/999999/reference", data={}).status_code == 404
