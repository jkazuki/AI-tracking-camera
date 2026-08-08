"""
geometry.py
Xử lý hình học: tính điểm chân (Foot Point) và kiểm tra vùng bằng Shapely.
"""

from shapely.geometry import Point, Polygon


def compute_foot_point(x1: float, y1: float, x2: float, y2: float):
    """
    Foot_Point = ((x1 + x2) / 2, y2)
    Điểm chính giữa mép dưới của Bounding Box -> mô phỏng vị trí đứng của thực thể.
    """
    fx = (x1 + x2) / 2.0
    fy = y2
    return fx, fy


def point_in_polygon(point_xy, polygon_points) -> bool:
    """
    point_xy: tuple (x, y)
    polygon_points: list các tuple [(x1,y1), (x2,y2), ...] tối thiểu 3 điểm
    Trả về True nếu điểm nằm trong (hoặc trên biên) đa giác.
    """
    if not polygon_points or len(polygon_points) < 3:
        return False
    poly = Polygon(polygon_points)
    if not poly.is_valid:
        # Một số đa giác vẽ tay có thể tự cắt nhau -> cố gắng sửa
        poly = poly.buffer(0)
    pt = Point(point_xy)
    return poly.contains(pt) or poly.touches(pt)


class Zone:
    """Đại diện cho một vùng đa giác đã đặt tên (A, B, hoặc C)."""

    def __init__(self, zone_id: str, zone_type: str, points):
        self.zone_id = zone_type      # "A", "B", "C"
        self.name = zone_id           # nhãn hiển thị, vd "A1", "B", "C1"
        self.points = points          # list[(x,y)]

    def contains(self, xy) -> bool:
        return point_in_polygon(xy, self.points)

    def to_dict(self):
        return {"zone_id": self.zone_id, "name": self.name, "points": self.points}

    @staticmethod
    def from_dict(d):
        return Zone(d["name"], d["zone_id"], [tuple(p) for p in d["points"]])
