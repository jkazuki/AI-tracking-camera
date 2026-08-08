"""
zone_editor.py
Cho phép người điều khiển nhấn giữ chuột trái, kéo vẽ tự do (free-hand)
và thả chuột trực tiếp trên Composite Canvas để tạo các vùng đa giác
(Vùng A - Sub-Zone, Vùng B - Master Zone, Vùng C - Restricted Zone).

Phím tắt trong lúc vẽ (nhấn trên cửa sổ OpenCV):
  a  -> chuyển chế độ vẽ sang Vùng A (sẽ hỏi tên vùng qua CMD1, vd A1, A2...)
  b  -> chuyển chế độ vẽ sang Vùng B (Master Zone, thường chỉ có 1 vùng B)
  c  -> chuyển chế độ vẽ sang Vùng C (Restricted Zone)
  s  -> lưu toàn bộ vùng hiện tại ra file zones.json
  z  -> xoá (undo) vùng vừa vẽ gần nhất
  q  -> thoát chế độ vẽ, bắt đầu giám sát
"""

import json
import cv2
import config
from geometry import Zone


class ZoneEditor:
    def __init__(self, canvas_width, canvas_height):
        self.canvas_width = canvas_width
        self.canvas_height = canvas_height
        self.zones: list[Zone] = []
        self.drawing = False
        self.current_points = []
        self.current_mode = "A"     # "A", "B", "C"
        self.pending_name_counter = {"A": 1, "B": 1, "C": 1}

    # ------------------------------------------------------------
    # Mouse callback: cv2.setMouseCallback(window, editor.on_mouse)
    # ------------------------------------------------------------
    def on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.current_points = [(x, y)]
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            # chỉ thêm điểm nếu đủ xa điểm trước đó, tránh đa giác quá dày
            last = self.current_points[-1]
            if abs(x - last[0]) + abs(y - last[1]) > 4:
                self.current_points.append((x, y))
        elif event == cv2.EVENT_LBUTTONUP:
            self.drawing = False
            if len(self.current_points) >= 3:
                self._finalize_zone()
            self.current_points = []

    def _finalize_zone(self):
        mode = self.current_mode
        idx = self.pending_name_counter[mode]
        name = f"{mode}{idx}" if mode != "B" else "B"
        self.pending_name_counter[mode] += 1
        zone = Zone(name, mode, list(self.current_points))
        self.zones.append(zone)
        print(f"[ZoneEditor] Đã tạo vùng {name} ({len(zone.points)} điểm)")

    # ------------------------------------------------------------
    # Điều khiển bàn phím trong lúc vẽ
    # ------------------------------------------------------------
    def handle_key(self, key: int) -> bool:
        """Trả về False nếu người dùng muốn thoát chế độ vẽ."""
        ch = chr(key & 0xFF) if key != -1 else ""
        if ch == "a":
            self.current_mode = "A"
            print("[ZoneEditor] Chế độ vẽ: Vùng A (Sub-Zone)")
        elif ch == "b":
            self.current_mode = "B"
            print("[ZoneEditor] Chế độ vẽ: Vùng B (Master Zone)")
        elif ch == "c":
            self.current_mode = "C"
            print("[ZoneEditor] Chế độ vẽ: Vùng C (Restricted Zone)")
        elif ch == "z":
            if self.zones:
                removed = self.zones.pop()
                print(f"[ZoneEditor] Đã xoá vùng {removed.name}")
        elif ch == "s":
            self.save()
        elif ch == "q":
            return False
        return True

    # ------------------------------------------------------------
    # Vẽ overlay lên canvas hiển thị
    # ------------------------------------------------------------
    def draw_overlay(self, frame):
        color_map = {"A": config.ZONE_COLOR_A, "B": config.ZONE_COLOR_B, "C": config.ZONE_COLOR_C}
        for zone in self.zones:
            pts = zone.points
            color = color_map.get(zone.zone_id, config.COLOR_WHITE)
            for i in range(len(pts)):
                p1 = pts[i]
                p2 = pts[(i + 1) % len(pts)]
                cv2.line(frame, p1, p2, color, 2)
            if pts:
                cv2.putText(frame, zone.name, pts[0], cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        if self.drawing and len(self.current_points) > 1:
            for i in range(len(self.current_points) - 1):
                cv2.line(frame, self.current_points[i], self.current_points[i + 1], (255, 255, 255), 1)
        return frame

    # ------------------------------------------------------------
    # Lưu / tải vùng từ JSON
    # ------------------------------------------------------------
    def save(self, path=None):
        path = path or config.ZONES_SAVE_PATH
        with open(path, "w", encoding="utf-8") as f:
            json.dump([z.to_dict() for z in self.zones], f, ensure_ascii=False, indent=2)
        print(f"[ZoneEditor] Đã lưu {len(self.zones)} vùng vào {path}")

    def load(self, path=None) -> bool:
        path = path or config.ZONES_SAVE_PATH
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.zones = [Zone.from_dict(d) for d in data]
            print(f"[ZoneEditor] Đã tải {len(self.zones)} vùng từ {path}")
            return True
        except FileNotFoundError:
            return False

    def zones_by_type(self, zone_type: str):
        return [z for z in self.zones if z.zone_id == zone_type]
