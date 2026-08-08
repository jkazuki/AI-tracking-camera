"""
state_manager.py
Quản lý vòng đời & trạng thái của từng thực thể (entity) được theo dõi:

  Trạng thái 1: UNASSIGNED  (Chưa gán mã)     -> khung TRẮNG
  Trạng thái 2: PENDING     (Chưa xác minh)   -> khung VÀNG
  Trạng thái 3: VERIFIED    (Đã xác minh)     -> khung XANH LÁ
  Trạng thái 4: ALERT       (Vi phạm)         -> khung ĐỎ

Cũng quản lý Group ID, biệt danh, cơ chế tự động giải phóng mã khi thực thể
đã xác minh rời Vùng B quá thời gian T giây, cơ chế RE-ID (nối lại track bị
đứt bằng khuôn mặt -- xem reid.py) và bộ lọc vật thể tĩnh (giảm báo động giả
khi YOLOv8 nhận nhầm đồ vật thành người).

LƯU Ý: gán Vùng A cho 1 thực thể là TUỲ CHỌN. Có thể chỉ xác minh (verified)
hoặc chỉ đặt biệt danh (nickname) mà không cần gán vùng A nào cả -- thực thể
đó vẫn được quản lý bình thường, chỉ là sẽ không có cảnh báo "rời Vùng A".
"""

import time
from dataclasses import dataclass, field
from enum import Enum
import config


class EntityState(Enum):
    UNASSIGNED = "UNASSIGNED"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    ALERT = "ALERT"


@dataclass
class Entity:
    track_id: int                      # ID nội bộ do YOLOv8/ByteTrack cấp (đổi khi track bị đứt)
    display_id: int = None             # ID đơn giản 1,2,3... do chương trình TỰ ĐẶT, ỔN ĐỊNH lâu dài (dùng để gõ lệnh)
    code: str = None                   # Mã vùng dạng Ax-y (vd A1-1) -- CHỈ có nếu đã gán Vùng A (tuỳ chọn)
    nickname: str = None               # Biệt danh do người điều khiển đặt (tuỳ chọn)
    group_id: str = None               # Mã nhóm nếu có (vd G1)
    state: EntityState = EntityState.UNASSIGNED
    current_zone_a: str = None         # Tên Vùng A hiện tại thực thể thuộc về (None nếu không gán vùng)
    last_seen_in_zone_a: float = field(default_factory=time.time)
    left_zone_a_at: float = None       # Mốc thời gian rời Vùng A (để tính grace period)
    left_zone_b_at: float = None       # Mốc thời gian rời Vùng B (để tính timeout 30s)
    in_zone_c: bool = False
    last_update: float = field(default_factory=time.time)
    position_history: list = field(default_factory=list)  # [(t, x, y), ...] -- dùng để lọc vật thể tĩnh

    @property
    def display_code(self):
        """Ưu tiên hiển thị: biệt danh > mã vùng > NEW_ID."""
        base = self.nickname or self.code
        if base:
            return f"{base}-{self.group_id}" if self.group_id else base
        return f"NEW_ID:{self.display_id}"


class EntityManager:
    def __init__(self, on_event=None):
        """
        on_event: callback(event_type: str, entity: Entity, extra: dict)
                  dùng để đẩy log lên CMD 1 (Bảng thông báo).
        """
        self.entities: dict[int, Entity] = {}   # key = track_id (đổi khi Re-ID nối lại track)
        self.code_to_track_id: dict[str, int] = {}
        self.display_id_to_track_id: dict[int, int] = {}
        self._next_display_id = 1               # bộ đếm ID hiển thị (1, 2, 3...) tự động, ỔN ĐỊNH, không trùng track_id
        self.on_event = on_event or (lambda *a, **k: None)

    # ---------------------------------------------------------------
    # Vòng đời cơ bản
    # ---------------------------------------------------------------
    def ensure_entity(self, track_id: int) -> Entity:
        if track_id not in self.entities:
            display_id = self._next_display_id
            self._next_display_id += 1
            e = Entity(track_id=track_id, display_id=display_id)
            self.entities[track_id] = e
            self.display_id_to_track_id[display_id] = track_id
            self.on_event("NEW_ENTITY", e, {})
        return self.entities[track_id]

    def reid_restore(self, display_id: int, new_track_id: int) -> Entity:
        """
        RE-ID: nối track_id MỚI (do ByteTrack cấp lại sau khi bị đứt track) vào
        đúng thực thể CŨ đã biết qua so khớp khuôn mặt (xem reid.py), giữ nguyên
        display_id/code/nickname/group/trạng thái xác minh -- không tạo NEW_ID mới.
        """
        old_track_id = self.display_id_to_track_id.get(display_id)
        if old_track_id is None or old_track_id not in self.entities:
            return self.ensure_entity(new_track_id)  # phòng hờ: không có gì để nối -> coi là mới
        if old_track_id == new_track_id:
            return self.entities[new_track_id]

        e = self.entities.pop(old_track_id)
        e.track_id = new_track_id
        e.position_history = []  # reset lịch sử vị trí vì có thể đã "nhảy cóc" vị trí lúc đứt track
        self.entities[new_track_id] = e
        self.display_id_to_track_id[display_id] = new_track_id
        if e.code:
            self.code_to_track_id[e.code] = new_track_id
        self.on_event("REID_RESTORED", e, {})
        return e

    def bind(self, track_id: int, code: str, group_id: str = None) -> bool:
        """Lệnh CMD2 (dạng đầy đủ, dùng track_id nội bộ): bind <track_id> <mã_Ax-y> [mã_nhóm]"""
        if track_id not in self.entities:
            return False
        e = self.entities[track_id]
        e.code = code
        e.group_id = group_id
        e.state = EntityState.PENDING
        e.current_zone_a = code.split("-")[0]  # vd "A1-1" -> "A1"
        self.code_to_track_id[code] = track_id
        self.on_event("BIND", e, {})
        return True

    def assign_by_display_id(self, display_id: int, zone_code: str = None,
                              verified: bool = False, nickname: str = None) -> bool:
        """
        Lệnh CMD2 (dạng nhanh): "<ID>[-<mã vùng>][.Y][/<biệt danh>]"
        Tất cả đều TUỲ CHỌN trừ ID -- chỉ cần gõ ít nhất 1 trong 3: vùng, xác minh, biệt danh.
        vd: "1-A1" (chỉ gán vùng) | "1.Y" (chỉ xác minh) | "1/Kz" (chỉ đặt biệt danh)
            "1-A1.Y" (gán vùng + xác minh) | "1-A1/Kz" (gán vùng + biệt danh)
        """
        track_id = self.display_id_to_track_id.get(display_id)
        if track_id is None:
            return False
        e = self.entities[track_id]

        if zone_code:
            code = f"{zone_code}-{display_id}"
            e.code = code
            e.current_zone_a = zone_code
            self.code_to_track_id[code] = track_id
            if e.state == EntityState.UNASSIGNED:
                e.state = EntityState.PENDING

        if nickname:
            e.nickname = nickname

        if verified:
            e.state = EntityState.VERIFIED
            e.left_zone_a_at = None

        self.on_event("ASSIGN", e, {})
        return True

    def mark_safe(self, code: str) -> bool:
        """Xác minh an toàn theo mã vùng (dùng nội bộ / nâng cao): safe <mã_Ax-y>"""
        track_id = self.code_to_track_id.get(code)
        if track_id is None or track_id not in self.entities:
            return False
        e = self.entities[track_id]
        e.state = EntityState.VERIFIED
        e.left_zone_a_at = None
        self.on_event("VERIFIED", e, {})
        return True

    def delete_by_code(self, code: str) -> bool:
        """Xóa thủ công theo mã vùng: del <mã_Ax-y>"""
        track_id = self.code_to_track_id.pop(code, None)
        if track_id is None:
            return False
        return self._delete_track(track_id)

    def delete_by_display_id(self, display_id: int) -> bool:
        """Xóa thủ công theo ID hiển thị: del <ID>"""
        track_id = self.display_id_to_track_id.pop(display_id, None)
        if track_id is None:
            return False
        return self._delete_track(track_id)

    def _delete_track(self, track_id: int) -> bool:
        e = self.entities.pop(track_id, None)
        if e is None:
            return False
        if e.code:
            self.code_to_track_id.pop(e.code, None)
        self.on_event("DELETED", e, {})
        return True

    def list_entities(self):
        return list(self.entities.values())

    # ---------------------------------------------------------------
    # Cập nhật trạng thái theo vị trí Foot Point mỗi frame
    # ---------------------------------------------------------------
    def update_zone_membership(self, track_id: int, in_zone_a: bool, in_zone_b: bool, in_zone_c: bool,
                                foot_point=None):
        e = self.ensure_entity(track_id)
        now = time.time()
        e.last_update = now

        # --- Lọc vật thể tĩnh: nếu 1 thực thể CHƯA GÁN GÌ CẢ đứng yên quá lâu,
        #     khả năng cao YOLOv8 đang nhận nhầm 1 đồ vật tĩnh thành người -> tự xoá ---
        if config.STATIC_OBJECT_FILTER_ENABLED and foot_point is not None and e.state == EntityState.UNASSIGNED:
            fx, fy = foot_point
            e.position_history.append((now, fx, fy))
            cutoff = now - config.STATIC_OBJECT_WINDOW_SEC
            e.position_history = [p for p in e.position_history if p[0] >= cutoff]
            if len(e.position_history) >= 2:
                xs = [p[1] for p in e.position_history]
                ys = [p[2] for p in e.position_history]
                spread = max(max(xs) - min(xs), max(ys) - min(ys))
                span_sec = e.position_history[-1][0] - e.position_history[0][0]
                if spread < config.STATIC_OBJECT_MOVEMENT_PX and span_sec >= config.STATIC_OBJECT_CONFIRM_SEC:
                    self.on_event("AUTO_REMOVED_STATIC_OBJECT", e, {})
                    self.entities.pop(track_id, None)
                    return

        # --- Vùng C: cảnh báo ghi nhận bất kể trạng thái xác minh ---
        if in_zone_c and not e.in_zone_c:
            self.on_event("ENTER_ZONE_C", e, {})
        e.in_zone_c = in_zone_c

        # --- Vùng A: CHỈ áp dụng nếu thực thể ĐÃ ĐƯỢC GÁN vùng A (current_zone_a có giá trị).
        #     Nếu không gán vùng A (chỉ verify/nickname suông) thì bỏ qua logic này hoàn toàn. ---
        if e.current_zone_a and e.state in (EntityState.PENDING, EntityState.ALERT):
            if in_zone_a:
                e.left_zone_a_at = None
                if e.state == EntityState.ALERT:
                    e.state = EntityState.PENDING
                    self.on_event("RETURNED_TO_ZONE_A", e, {})
            else:
                if e.left_zone_a_at is None:
                    e.left_zone_a_at = now
                elapsed = now - e.left_zone_a_at
                if elapsed > config.ALERT_GRACE_PERIOD_SEC and e.state != EntityState.ALERT:
                    e.state = EntityState.ALERT
                    self.on_event("ALERT_LEFT_ZONE_A", e, {})

        # --- Vùng B: áp dụng cho cả VERIFIED lẫn chưa xác minh (theo dõi timeout) ---
        if in_zone_b:
            e.left_zone_b_at = None
        else:
            if e.left_zone_b_at is None:
                e.left_zone_b_at = now
            elapsed_b = now - e.left_zone_b_at
            if e.state == EntityState.VERIFIED and elapsed_b > config.ZONE_B_RELEASE_TIMEOUT_SEC:
                self.on_event("AUTO_RELEASE_ZONE_B_TIMEOUT", e, {})
                if e.code:
                    self.code_to_track_id.pop(e.code, None)
                self.entities.pop(track_id, None)
            elif e.state != EntityState.VERIFIED and elapsed_b > 0:
                # thực thể chưa xác minh rời hẳn Vùng B lớn -> ứng viên cho Mức 2 (xử lý ở alerts.py)
                self.on_event("LEFT_ZONE_B_UNVERIFIED", e, {})

    def get_color(self, e: Entity):
        return {
            EntityState.UNASSIGNED: config.COLOR_WHITE,
            EntityState.PENDING: config.COLOR_YELLOW,
            EntityState.VERIFIED: config.COLOR_GREEN,
            EntityState.ALERT: config.COLOR_RED,
        }[e.state]
