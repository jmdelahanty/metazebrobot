"""Heritage lineage graph and page (docs/tank_heritage_design.md step 3)."""

import uuid

from metazebrobot.utils.heritage_graph import build_heritage_graph, layout_heritage_graph
from metazebrobot.utils.tank_origins import resolve_tank_origins

from tests.test_tank_origins import (  # noqa: F401  (conn fixture)
    CROSS_13000,
    TestResolveTankOrigins,
    cacher,
    conn,
    crossing,
    target_cross,
)


def resolved(conn):
    target_cross(conn)
    resolve_tank_origins(conn, TestResolveTankOrigins().client(), cacher(conn), ["6728"])


def edge_set(graph):
    return {(e["source"], e["target"], e["kind"]) for e in graph["edges"]}


class TestBuildHeritageGraph:
    def test_split_cross_and_parents(self, conn):
        resolved(conn)
        graph = build_heritage_graph(conn, 6728)
        nodes = {n["id"]: n for n in graph["nodes"]}

        assert nodes["tank:6728"]["role"] == "subject"
        assert nodes["tank:6728"]["origin"] == "split"
        assert nodes["cross:14979"]["cross_type"] == "outcross"
        assert {
            ("tank:6643", "tank:6728", "split"),
            ("cross:14979", "tank:6643", "produced"),
            ("tank:6190", "cross:14979", "parent"),
            ("tank:4014", "cross:14979", "parent"),
            ("cross:13000", "tank:6190", "produced"),
            ("tank:5000", "cross:13000", "parent"),
        } <= edge_set(graph)
        assert graph["truncated"] is False

    def test_generation_limit_truncates(self, conn):
        resolved(conn)
        graph = build_heritage_graph(conn, 6728, generations=1)
        nodes = {n["id"]: n for n in graph["nodes"]}
        assert "cross:13000" not in nodes
        assert nodes["tank:6190"]["origin"] == "not expanded"
        assert graph["truncated"] is True

    def test_shared_ancestor_appears_once(self, conn):
        # Two parents produced by the same cross: that cross is one node.
        cacher(conn)([
            crossing(1, [{"tank_id": 10, "strain_name": "AB", "strain_id": 29}],
                     [{"tank_id": 20, "strain_name": "AB", "strain_id": 29},
                      {"tank_id": 21, "strain_name": "AB", "strain_id": 29}]),
            crossing(2, [{"tank_id": 20, "strain_name": "AB", "strain_id": 29},
                         {"tank_id": 21, "strain_name": "AB", "strain_id": 29}],
                     [{"tank_id": 30, "strain_name": "AB", "strain_id": 29}]),
        ])
        graph = build_heritage_graph(conn, 30)
        assert [n["id"] for n in graph["nodes"]].count("cross:1") == 1
        assert len(edge_set(graph)) == len(graph["edges"])

    def test_tank_without_ancestry_is_a_single_node(self, conn):
        cacher(conn)([CROSS_13000])
        graph = build_heritage_graph(conn, 5000)
        assert [n["id"] for n in graph["nodes"]] == ["tank:5000"]
        assert graph["edges"] == []


class TestLayout:
    def test_subject_left_and_every_edge_points_left(self, conn):
        resolved(conn)
        graph = layout_heritage_graph(build_heritage_graph(conn, 6728))
        nodes = {n["id"]: n for n in graph["nodes"]}
        assert nodes["tank:6728"]["x"] == min(n["x"] for n in graph["nodes"])
        for edge in graph["edges"]:
            assert nodes[edge["source"]]["x"] > nodes[edge["target"]]["x"], edge
        assert graph["width"] > 0 and graph["height"] > 0

    def test_empty_graph(self):
        assert layout_heritage_graph({"nodes": [], "edges": []})["width"] == 0


class TestHeritageRoutes:
    def cache_family(self):
        import metazebrobot.api_server as api_server

        base = 70000 + uuid.uuid4().int % 9000
        parent_cross, child_cross = str(base), str(base + 1)
        api_server._cache_cross_rows([
            {"crossing_id": parent_cross, "date_of_set_up": "2025-12-22T08:00:00",
             "tanks": {"parents": [{"tank_id": base + 100, "strain_name": "AB Casper_HHMI",
                                    "strain_id": 14}],
                       "children": [{"tank_id": base + 200, "strain_name": "Casper_HHMI [AB-C] DEC25",
                                     "strain_id": 1532, "date_of_birth": "2025-12-23T00:00:00"}]}},
            {"crossing_id": child_cross, "date_of_set_up": "2026-03-09T08:00:00",
             "tanks": {"parents": [{"tank_id": base + 200, "strain_name": "Casper_HHMI [AB-C] DEC25",
                                    "strain_id": 1532}],
                       "children": [{"tank_id": base + 300, "strain_name": "Casper_HHMI [AB-C IC] MAR26",
                                     "strain_id": 1574, "date_of_birth": "2026-03-10T00:00:00"}]}},
        ])
        return base, parent_cross, child_cross

    def test_heritage_api_and_page(self, client):
        base, parent_cross, child_cross = self.cache_family()
        tank = str(base + 300)

        payload = client.get(f"/tanks/{tank}/heritage").json()
        assert payload["heritage"]["producing_cross"]["cross_id"] == child_cross
        assert payload["heritage"]["label_checks"]["incross"] is True
        assert {n["id"] for n in payload["graph"]["nodes"]} >= {
            f"tank:{tank}", f"cross:{child_cross}", f"cross:{parent_cross}"}

        page = client.get(f"/tanks/{tank}/heritage/")
        assert page.status_code == 200
        assert f"Heritage - Tank {tank}" in page.text
        assert "<svg" in page.text
        assert f'href="/crosses/{child_cross}/provenance/"' in page.text
        assert "label matches records" in page.text

    def test_unknown_tank_is_structured_404(self, client):
        response = client.get("/tanks/987654321/heritage")
        assert response.status_code == 404
        assert response.json()["detail"] == {"error": "tank_not_found", "tank_id": "987654321"}

    def test_provenance_page_links_parent_heritage(self, client):
        base, _, child_cross = self.cache_family()
        page = client.get(f"/crosses/{child_cross}/provenance/").text
        assert f'href="/tanks/{base + 200}/heritage/"' in page
