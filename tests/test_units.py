from book_gutter.units import mm_to_points, points_to_mm


def test_mm_point_roundtrip():
    assert abs(points_to_mm(mm_to_points(10.0)) - 10.0) < 1e-9
