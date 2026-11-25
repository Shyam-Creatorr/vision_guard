from app.services.box_math import bbox_1000_to_pixels, clamp_bbox_1000


def test_clamp_and_degenerate_boxes():
    assert clamp_bbox_1000([-20, 50, 1200, 950]) == [0, 50, 1000, 950]
    assert clamp_bbox_1000([500, 100, 500, 300]) is None  # zero height
    assert clamp_bbox_1000([100, 400, 200, 300]) is None  # xmin > xmax
    assert clamp_bbox_1000([100, 100, 102, 102]) is None  # microscopic


def test_pixel_conversion():
    px = bbox_1000_to_pixels([250, 100, 750, 900], width_px=1200, height_px=800)
    assert px == [120, 200, 1080, 600]
