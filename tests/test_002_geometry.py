"""TEST-002 Geometry: primitives and engine functions (spec sections 9, 97)."""

from __future__ import annotations

import unittest

from core.errors import GeometryError
from core.geometry import engine as ge
from core.geometry.primitives import Circle, Line, Point, Polygon, Polyline
from core.geometry.repair import FixKind, GeometryRepairEngine, IssueKind


class TestGeometry(unittest.TestCase):
    def test_point_distance(self):
        self.assertAlmostEqual(Point(0, 0).distance_to(Point(3, 4)), 5.0, places=9)

    def test_line_angle(self):
        line = Line(Point(0, 0), Point(10, 0))
        self.assertAlmostEqual(line.angle_deg(), 0.0, places=6)
        self.assertAlmostEqual(Line(Point(0, 0), Point(0, 5)).angle_deg(), 90.0, places=6)

    def test_area_perimeter_centroid(self):
        poly = Polygon([Point(0, 0), Point(4, 0), Point(4, 3), Point(0, 3)])
        self.assertAlmostEqual(ge.area(poly), 12.0, places=9)
        self.assertAlmostEqual(ge.perimeter(poly), 14.0, places=9)
        c = ge.centroid(poly.points)
        self.assertAlmostEqual(c.x, 2.0, places=9)
        self.assertAlmostEqual(c.y, 1.5, places=9)

    def test_area_orientation_invariant(self):
        a = Polygon([Point(0, 0), Point(4, 0), Point(4, 3), Point(0, 3)])
        b = Polygon(list(reversed(a.points)))
        self.assertAlmostEqual(ge.area(a), ge.area(b), places=9)

    def test_contains(self):
        poly = Polygon([Point(0, 0), Point(4, 0), Point(4, 3), Point(0, 3)])
        self.assertTrue(ge.contains(poly, Point(1, 1)))
        self.assertFalse(ge.contains(poly, Point(5, 5)))

    def test_line_intersection(self):
        inter = ge.intersection(Line(Point(-1, 1), Point(11, 1)),
                                Line(Point(5, -1), Point(5, 5)))
        self.assertIsNotNone(inter)
        self.assertAlmostEqual(inter.x, 5.0, places=9)
        self.assertIsNone(ge.intersection(Line(Point(0, 0), Point(1, 0)),
                                          Line(Point(0, 1), Point(1, 1))))

    def test_polygon_clip_overlap(self):
        a = Polygon([Point(0, 0), Point(4, 0), Point(4, 4), Point(0, 4)])
        b = Polygon([Point(2, 2), Point(6, 2), Point(6, 6), Point(2, 6)])
        self.assertAlmostEqual(ge.overlap_area(a, b), 4.0, places=6)
        self.assertTrue(ge.overlaps(a, b))
        c = Polygon([Point(10, 10), Point(14, 10), Point(14, 14), Point(10, 14)])
        self.assertFalse(ge.overlaps(a, c))

    def test_transforms(self):
        poly = Polygon([Point(0, 0), Point(4, 0), Point(4, 3), Point(0, 3)])
        moved = ge.translate(poly, 10, 20)
        self.assertAlmostEqual(moved.points[0].x, 10.0)
        rotated = ge.rotate(poly, Point(0, 0), 90)
        self.assertAlmostEqual(rotated.points[1].x, 0.0, places=6)
        self.assertAlmostEqual(rotated.points[1].y, 4.0, places=6)
        mirrored = ge.mirror(poly, Point(0, 0), Point(0, 1))
        self.assertAlmostEqual(mirrored.points[0].x, 0.0, places=6)
        self.assertAlmostEqual(mirrored.points[1].x, -4.0, places=6)
        scaled = ge.scale(poly, Point(0, 0), 2.0)
        self.assertAlmostEqual(ge.area(scaled), 48.0, places=6)

    def test_wall_outline(self):
        outline = ge.wall_outline(Line(Point(0, 0), Point(5, 0)), 0.2)
        self.assertAlmostEqual(ge.area(outline), 1.0, places=9)

    def test_split_and_offset(self):
        l1, l2 = ge.split(Line(Point(0, 0), Point(10, 0)), Point(4, 0))
        self.assertAlmostEqual(l1.length, 4.0, places=9)
        self.assertAlmostEqual(l2.length, 6.0, places=9)
        with self.assertRaises(GeometryError):
            ge.split(Line(Point(0, 0), Point(10, 0)), Point(4, 5))
        offset = ge.offset(Line(Point(0, 0), Point(10, 0)), 1.0)
        self.assertAlmostEqual(offset.start.y, 1.0, places=9)

    def test_trim_extend(self):
        trimmed = ge.trim(Line(Point(0, 0), Point(10, 0)), Line(Point(5, -5), Point(5, 5)),
                          keep="start")
        self.assertAlmostEqual(trimmed.end.x, 5.0, places=9)
        extended = ge.extend(Line(Point(0, 0), Point(3, 0)), Line(Point(7, -7), Point(7, 7)))
        self.assertAlmostEqual(extended.end.x, 7.0, places=9)

    def test_project_nearest_bounding(self):
        proj = ge.project(Point(3, 7), Line(Point(0, 0), Point(10, 0)))
        self.assertAlmostEqual(proj.y, 0.0, places=9)
        nearest = ge.nearest_point(Line(Point(0, 0), Point(10, 0)), Point(3, 4))
        self.assertAlmostEqual(nearest.x, 3.0, places=9)
        lo, hi = ge.bounding_box([Point(-1, 2), Point(3, 8)])
        self.assertEqual((lo.x, lo.y, hi.x, hi.y), (-1, 2, 3, 8))

    def test_circle(self):
        c = Circle(Point(0, 0), 2.0)
        self.assertAlmostEqual(ge.area(c), 12.566370614, places=6)
        self.assertAlmostEqual(ge.perimeter(c), 12.566370614, places=6)

    def test_join(self):
        pl1 = Polyline([Point(0, 0), Point(1, 0)])
        pl2 = Polyline([Point(1, 0), Point(2, 0)])
        joined = ge.join([pl1, pl2])
        self.assertEqual(len(joined.points), 3)

    def test_invalid_polygon_rejected(self):
        with self.assertRaises(GeometryError):
            Polygon([Point(0, 0), Point(1, 1)])


class TestGeometryRepair(unittest.TestCase):
    def test_detect_duplicate_vertices_and_zero_segment(self):
        engine = GeometryRepairEngine()
        points = [Point(0, 0), Point(0, 0), Point(4, 0), Point(4, 0), Point(4, 3), Point(0, 3)]
        issues = engine.detect(points, closed=True)
        kinds = {i.kind for i in issues}
        self.assertIn(IssueKind.DUPLICATED_VERTEX, kinds)
        self.assertIn(IssueKind.ZERO_SEGMENT, kinds)

    def test_repair_flow_with_approval(self):
        engine = GeometryRepairEngine()
        points = [Point(0, 0), Point(0, 0), Point(4, 0), Point(4, 3), Point(0, 3)]
        issues = engine.detect(points, closed=True, object_ref="W-1")
        proposals = engine.propose(points, closed=True, issues=issues, object_ref="W-1")
        self.assertTrue(proposals)
        # Without approval nothing changes
        report_no = engine.apply(points, closed=True, proposals=proposals, approved=False)
        self.assertEqual(len(report_no.applied), 0)
        # With approval the vertices are fixed and revalidated
        report = engine.apply(points, closed=True, proposals=proposals, approved=True)
        self.assertTrue(report.applied)
        self.assertTrue(report.revalidated_clean, report.remaining_issues)

    def test_self_intersection_flagged_not_auto_fixed(self):
        engine = GeometryRepairEngine()
        bowtie = [Point(0, 0), Point(4, 4), Point(4, 0), Point(0, 4)]
        issues = engine.detect(bowtie, closed=True)
        self.assertIn(IssueKind.SELF_INTERSECTION, {i.kind for i in issues})
        proposals = engine.propose(bowtie, closed=True, issues=issues)
        self.assertIn(FixKind.MARK_FOR_REVIEW, {p.fix_kind for p in proposals})


if __name__ == "__main__":
    unittest.main()
