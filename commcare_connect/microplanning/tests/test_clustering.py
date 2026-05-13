import pytest
from django.contrib.gis.geos import Point, Polygon

from commcare_connect.microplanning.clustering import WorkAreaGrouper
from commcare_connect.microplanning.models import SRID, WorkAreaGroup
from commcare_connect.microplanning.tests.factories import WorkAreaFactory


@pytest.mark.django_db
class TestWorkAreaGrouper:
    def create_adjacent_work_areas(
        self,
        opportunity,
        ward,
        start_x=77.0,
        start_y=28.0,
        size=0.01,
        slug_prefix="area",
    ):
        work_areas = []

        # Create a 2x2 grid of adjacent work areas
        positions = [
            (start_x, start_y),  # Bottom-left
            (start_x + size, start_y),  # Bottom-right
            (start_x, start_y + size),  # Top-left
            (start_x + size, start_y + size),  # Top-right
        ]

        for idx, (x, y) in enumerate(positions):
            boundary = Polygon(
                (
                    (x, y),
                    (x + size, y),
                    (x + size, y + size),
                    (x, y + size),
                    (x, y),
                ),
                srid=SRID,
            )
            centroid = Point(x + size / 2, y + size / 2, srid=SRID)

            work_area = WorkAreaFactory(
                opportunity=opportunity,
                slug=f"{slug_prefix}-{ward}-{idx}",
                ward=ward,
                centroid=centroid,
                boundary=boundary,
                building_count=50,  # Small enough to fit multiple in one group
            )
            work_areas.append(work_area)

        return work_areas

    def test_cluster_adjacent_work_areas(self, opportunity):
        work_areas = self.create_adjacent_work_areas(opportunity, ward="ward-1")

        grouper = WorkAreaGrouper(opportunity_id=opportunity.id, max_buildings=300)
        grouper.cluster_work_areas()

        work_area_groups = WorkAreaGroup.objects.filter(opportunity=opportunity)

        assert work_area_groups.exists()
        assert work_area_groups.count() == 1
        for work_area in work_areas:
            work_area.refresh_from_db()
            assert work_area.work_area_group_id == work_area_groups[0].id

    def test_cluster_respects_max_buildings(self, opportunity):
        work_areas = self.create_adjacent_work_areas(opportunity, ward="ward-1")
        for wa in work_areas:
            wa.building_count = 100
            wa.save()

        grouper = WorkAreaGrouper(opportunity_id=opportunity.id, max_buildings=150)
        grouper.cluster_work_areas()

        work_area_groups = WorkAreaGroup.objects.filter(opportunity=opportunity)

        assert work_area_groups.count() == 4
        for group in work_area_groups:
            assert group.building_count <= 150

    def test_cluster_multiple_wards_separately(self, opportunity):
        # Create work areas in two different wards
        ward1_areas = self.create_adjacent_work_areas(opportunity, ward="ward-1", start_x=77.0, slug_prefix="w1")
        ward2_areas = self.create_adjacent_work_areas(opportunity, ward="ward-2", start_x=78.0, slug_prefix="w2")

        grouper = WorkAreaGrouper(opportunity_id=opportunity.id, max_buildings=300)
        grouper.cluster_work_areas()

        work_area_groups = WorkAreaGroup.objects.filter(opportunity=opportunity)

        assert work_area_groups.count() >= 2

        wards = {wag.ward for wag in work_area_groups}
        assert "ward-1" in wards
        assert "ward-2" in wards

        ward1_group = WorkAreaGroup.objects.get(opportunity=opportunity, ward="ward-1")
        ward2_group = WorkAreaGroup.objects.get(opportunity=opportunity, ward="ward-2")

        for work_area in ward1_areas:
            work_area.refresh_from_db()
            assert work_area.work_area_group == ward1_group

        for work_area in ward2_areas:
            work_area.refresh_from_db()
            assert work_area.work_area_group == ward2_group

    def test_cluster_empty_opportunity(self, opportunity):
        grouper = WorkAreaGrouper(opportunity_id=opportunity.id)
        grouper.cluster_work_areas()
        assert not WorkAreaGroup.objects.filter(opportunity=opportunity).exists()

    def test_cluster_single_work_area(self, opportunity):
        work_area = WorkAreaFactory(
            opportunity=opportunity,
            slug="area-1",
            ward="ward-1",
            centroid=Point(77.5, 28.5, srid=SRID),
            boundary=Polygon(
                ((77.0, 28.0), (78.0, 28.0), (78.0, 29.0), (77.0, 29.0), (77.0, 28.0)),
                srid=SRID,
            ),
            building_count=100,
        )

        grouper = WorkAreaGrouper(opportunity_id=opportunity.id)
        grouper.cluster_work_areas()

        work_area_groups = WorkAreaGroup.objects.filter(opportunity=opportunity)

        assert work_area_groups.count() == 1
        work_area.refresh_from_db()
        assert work_area.work_area_group == work_area_groups[0]

    def test_cluster_idempotent(self, opportunity):
        self.create_adjacent_work_areas(opportunity, ward="ward-1")

        grouper = WorkAreaGrouper(opportunity_id=opportunity.id, max_buildings=300)
        grouper.cluster_work_areas()

        assert WorkAreaGroup.objects.filter(opportunity=opportunity).count() == 1

        # Running again should be a no-op
        grouper.cluster_work_areas()

        assert WorkAreaGroup.objects.filter(opportunity=opportunity).count() == 1

    def test_cluster_excludes_zero_building_count(self, opportunity):
        work_area = WorkAreaFactory(
            opportunity=opportunity,
            slug="zero-buildings",
            ward="ward-1",
            centroid=Point(77.5, 28.5, srid=SRID),
            boundary=Polygon(
                ((77.0, 28.0), (78.0, 28.0), (78.0, 29.0), (77.0, 29.0), (77.0, 28.0)),
                srid=SRID,
            ),
            building_count=0,
        )

        grouper = WorkAreaGrouper(opportunity_id=opportunity.id)
        grouper.cluster_work_areas()

        assert not WorkAreaGroup.objects.filter(opportunity=opportunity).exists()
        work_area.refresh_from_db()
        assert work_area.work_area_group is None

    def test_cluster_corner_sharing_work_areas(self, opportunity):
        """Work areas sharing only a corner (point) must NOT be grouped together.
        Diagonal-only neighbors aren't meaningfully contiguous — adjacency requires
        a shared edge (dim >= 1) or strictly-positive distance within buffer_distance."""
        size = 0.01
        # Create two squares that touch only at a corner point
        wa1 = WorkAreaFactory(
            opportunity=opportunity,
            slug="corner-1",
            ward="ward-1",
            centroid=Point(77.0 + size / 2, 28.0 + size / 2, srid=SRID),
            boundary=Polygon(
                ((77.0, 28.0), (77.0 + size, 28.0), (77.0 + size, 28.0 + size), (77.0, 28.0 + size), (77.0, 28.0)),
                srid=SRID,
            ),
            building_count=50,
        )
        wa2 = WorkAreaFactory(
            opportunity=opportunity,
            slug="corner-2",
            ward="ward-1",
            centroid=Point(77.0 + size + size / 2, 28.0 + size + size / 2, srid=SRID),
            boundary=Polygon(
                (
                    (77.0 + size, 28.0 + size),
                    (77.0 + 2 * size, 28.0 + size),
                    (77.0 + 2 * size, 28.0 + 2 * size),
                    (77.0 + size, 28.0 + 2 * size),
                    (77.0 + size, 28.0 + size),
                ),
                srid=SRID,
            ),
            building_count=50,
        )

        grouper = WorkAreaGrouper(opportunity_id=opportunity.id, max_buildings=300)
        grouper.cluster_work_areas()

        groups = WorkAreaGroup.objects.filter(opportunity=opportunity)
        assert groups.count() == 2

        wa1.refresh_from_db()
        wa2.refresh_from_db()
        assert wa1.work_area_group != wa2.work_area_group

    def test_cluster_single_work_area_exceeding_max_buildings(self, opportunity):
        work_area = WorkAreaFactory(
            opportunity=opportunity,
            slug="large-area",
            ward="ward-1",
            centroid=Point(77.5, 28.5, srid=SRID),
            boundary=Polygon(
                ((77.0, 28.0), (78.0, 28.0), (78.0, 29.0), (77.0, 29.0), (77.0, 28.0)),
                srid=SRID,
            ),
            building_count=500,
        )

        grouper = WorkAreaGrouper(opportunity_id=opportunity.id, max_buildings=300)
        grouper.cluster_work_areas()

        # Should still create a group for the oversized work area
        group = WorkAreaGroup.objects.get(opportunity=opportunity)
        assert group.building_count == 500
        work_area.refresh_from_db()
        assert work_area.work_area_group == group

    def test_cluster_respects_max_work_areas(self, opportunity):
        """4 adjacent WAs (200 buildings total) with max_work_areas=2 should split into 2 groups
        of 2 WAs each. The building cap (default 300) does not trip — only the count cap does."""
        work_areas = self.create_adjacent_work_areas(opportunity, ward="ward-1")
        # create_adjacent_work_areas sets building_count=50 per WA; total = 200, well under 300.

        grouper = WorkAreaGrouper(
            opportunity_id=opportunity.id,
            max_buildings=300,
            max_work_areas=2,
        )
        grouper.cluster_work_areas()

        groups = WorkAreaGroup.objects.filter(opportunity=opportunity)
        assert groups.count() == 2
        for group in groups:
            assert group.workarea_set.count() == 2

        for work_area in work_areas:
            work_area.refresh_from_db()
            assert work_area.work_area_group is not None

    def test_cluster_no_bridging_across_wide_gap(self, opportunity):
        """Two pairs of edge-sharing WAs separated by a ~33m gap should produce 2 groups, not 1.

        Input coordinates are in EPSG:4326 (degrees); the clustering algorithm projects them
        to EPSG:3857 (Web Mercator meters) for distance math. At the equator the conversion
        is ~0.0003° longitude → ~33 m of projected distance — wider than the default
        buffer_distance (10 m) but narrower than the previous default (100 m). Pins the fix
        for CCCT-2392 Part 1: clusters must not bridge realistic inter-region gaps."""
        size = 0.001  # 4326 degrees; projects to ~111 m squares in EPSG:3857
        gap = 0.0003  # 4326 degrees; ~33 m gap in EPSG:3857 — between new (10 m) and old (100 m) defaults

        start_a = 77.0
        start_b = start_a + 2 * size + gap

        for x_start, slug in [
            (start_a, "a1"),
            (start_a + size, "a2"),
            (start_b, "b1"),
            (start_b + size, "b2"),
        ]:
            x_end = x_start + size
            WorkAreaFactory(
                opportunity=opportunity,
                slug=f"area-{slug}",
                ward="ward-1",
                centroid=Point(x_start + size / 2, 28.0 + size / 2, srid=SRID),
                boundary=Polygon(
                    ((x_start, 28.0), (x_end, 28.0), (x_end, 28.0 + size), (x_start, 28.0 + size), (x_start, 28.0)),
                    srid=SRID,
                ),
                building_count=50,
            )

        grouper = WorkAreaGrouper(opportunity_id=opportunity.id)
        grouper.cluster_work_areas()

        groups = WorkAreaGroup.objects.filter(opportunity=opportunity)
        assert groups.count() == 2
        for group in groups:
            assert group.workarea_set.count() == 2

    def test_cluster_does_not_bridge_across_intervening_wa(self, opportunity):
        """5 WAs in a row, all sharing edges (A1-A2-X-B1-B2). X has a high building count
        that prevents BFS expansion through it.

        Without the blocker check: A2↔B1 forms an over-the-top adjacency edge (their nearest
        corners are within buffer_distance), letting BFS from A1 reach B1 by skipping over X.
        That would cluster {A1, A2, B1} together — physically separated by X — which is the
        bug this test pins.

        With the blocker check: the line from A2's nearest point to B1's nearest point passes
        through X's polygon, so the A2↔B1 edge is filtered. BFS routes only through shared
        edges. Result: {A1, A2}, {X}, {B1, B2}."""
        size = 0.00008  # 4326 degrees; ~8.9 m in EPSG:3857 — within default buffer_distance=10m
        layout = [
            ("a1", 0, 50),
            ("a2", 1, 50),
            ("x", 2, 200),
            ("b1", 3, 50),
            ("b2", 4, 50),
        ]

        created = []
        for slug, idx, buildings in layout:
            x_start = idx * size
            x_end = x_start + size
            wa = WorkAreaFactory(
                opportunity=opportunity,
                slug=f"area-{slug}",
                ward="ward-1",
                centroid=Point(x_start + size / 2, 28.0 + size / 2, srid=SRID),
                boundary=Polygon(
                    (
                        (x_start, 28.0),
                        (x_end, 28.0),
                        (x_end, 28.0 + size),
                        (x_start, 28.0 + size),
                        (x_start, 28.0),
                    ),
                    srid=SRID,
                ),
                building_count=buildings,
            )
            created.append(wa)

        grouper = WorkAreaGrouper(opportunity_id=opportunity.id, max_buildings=150)
        grouper.cluster_work_areas()

        for wa in created:
            wa.refresh_from_db()
        a1, a2, x, b1, b2 = created

        assert a1.work_area_group_id == a2.work_area_group_id
        assert b1.work_area_group_id == b2.work_area_group_id
        assert a1.work_area_group_id != b1.work_area_group_id
        assert x.work_area_group_id != a1.work_area_group_id
        assert x.work_area_group_id != b1.work_area_group_id
        assert WorkAreaGroup.objects.filter(opportunity=opportunity).count() == 3
