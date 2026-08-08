"""
alerts.py
Thang báo động theo cấp độ (Escalation Hierarchy):

  Mức 0: Bình thường          -> chữ trắng
  Mức 1: Báo động Cao (VÀNG)  -> TOÀN BỘ thực thể chưa xác minh cùng 1 Vùng A
                                   (hoặc cùng nhóm) đồng thời rời khỏi Vùng A đó
  Mức 2: Báo động Nguy Cấp    -> TẤT CẢ thực thể chưa xác minh (+ nhóm liên quan)
         (ĐỎ TỐI CAO)            bước ra khỏi Vùng B lớn -> chớp nháy (blinking)

Module này gom các Entity theo Vùng A / Group để tính toán khi nào một
nhóm/vùng đạt ngưỡng "TOÀN BỘ cùng rời" thay vì chỉ 1 cá nhân.
"""

from collections import defaultdict
from state_manager import EntityState
from config import Ansi


class AlertLevel:
    NORMAL = 0
    HIGH_YELLOW = 1
    CRITICAL_RED = 2


class EscalationEngine:
    def __init__(self, entity_manager):
        self.em = entity_manager
        self._last_level_by_group = {}

    def _grouping_key(self, e):
        """Nhóm theo group_id nếu có, ngược lại nhóm theo Vùng A (current_zone_a)."""
        if e.group_id:
            return f"G:{e.group_id}"
        return f"Z:{e.current_zone_a}" if e.current_zone_a else None

    def evaluate(self):
        """
        Trả về list các sự kiện escalation mới cần log:
        [{"level": 1 or 2, "key": group_key, "codes": [...]}, ...]
        Chỉ được gọi định kỳ (vd mỗi frame hoặc mỗi giây) sau khi
        state_manager đã cập nhật xong trạng thái từng entity trong frame đó.
        """
        groups = defaultdict(list)
        for e in self.em.list_entities():
            key = self._grouping_key(e)
            if key:
                groups[key].append(e)

        events = []
        for key, members in groups.items():
            unverified = [m for m in members if m.state in (EntityState.PENDING, EntityState.ALERT)]
            if not unverified:
                self._last_level_by_group[key] = AlertLevel.NORMAL
                continue
            all_left_a = all(m.state == EntityState.ALERT for m in unverified)
            all_left_b = all(m.left_zone_b_at is not None for m in unverified)

            if all_left_a and all_left_b:
                level = AlertLevel.CRITICAL_RED
            elif all_left_a:
                level = AlertLevel.HIGH_YELLOW
            else:
                level = AlertLevel.NORMAL

            if level != self._last_level_by_group.get(key, AlertLevel.NORMAL) and level != AlertLevel.NORMAL:
                events.append({
                    "level": level,
                    "key": key,
                    "codes": [m.display_code for m in unverified],
                })
            self._last_level_by_group[key] = level

        return events


def format_log_line(event_type: str, entity, extra: dict = None) -> str:
    """Định dạng 1 dòng log ANSI màu cho CMD 1 (Bảng thông báo), theo bảng mã màu mô tả trong thiết kế."""
    ts = extra.get("timestamp_str", "") if extra else ""
    code = entity.display_code

    if event_type == "NEW_ENTITY":
        return (f"{Ansi.WHITE}[{ts}] Thực thể mới vào Vùng B: NEW_ID:{entity.display_id} "
                f"- gõ '{entity.display_id}-<mã vùng>' hoặc '{entity.display_id}.Y' hoặc "
                f"'{entity.display_id}/<biệt danh>' trên CMD2 để gán{Ansi.RESET}")
    if event_type == "BIND":
        return f"{Ansi.WHITE}[{ts}] Đã gán mã {code} cho track_id={entity.track_id}{Ansi.RESET}"
    if event_type == "ASSIGN":
        parts = []
        if entity.code:
            parts.append(f"vùng {entity.current_zone_a}")
        if entity.nickname:
            parts.append(f"biệt danh '{entity.nickname}'")
        if entity.state == EntityState.VERIFIED:
            parts.append("đã XÁC MINH")
        detail = ", ".join(parts) if parts else "(không có thay đổi)"
        return f"{Ansi.WHITE}[{ts}] Đã cập nhật {code}: {detail}{Ansi.RESET}"
    if event_type == "VERIFIED":
        return f"{Ansi.WHITE}[{ts}] {code} đã được XÁC MINH (an toàn){Ansi.RESET}"
    if event_type == "REID_RESTORED":
        return (f"{Ansi.WHITE}[{ts}] Re-ID: nhận lại {code} bằng khuôn mặt "
                f"(track cũ bị đứt, đã tự nối lại, giữ nguyên vùng/biệt danh/trạng thái){Ansi.RESET}")
    if event_type == "AUTO_REMOVED_STATIC_OBJECT":
        return (f"{Ansi.WHITE}[{ts}] Tự động loại bỏ {code} -- đứng yên quá lâu, "
                f"khả năng là vật thể tĩnh bị nhận nhầm thành người{Ansi.RESET}")
    if event_type == "ENTER_ZONE_C":
        return f"{Ansi.ORANGE}[{ts}] CHÚ Ý: {code} đã đi vào Vùng C (khu vực nhạy cảm){Ansi.RESET}"
    if event_type == "ALERT_LEFT_ZONE_A":
        return f"{Ansi.YELLOW}[{ts}] CẢNH BÁO: {code} rời khỏi Vùng A khi CHƯA xác minh{Ansi.RESET}"
    if event_type == "RETURNED_TO_ZONE_A":
        return f"{Ansi.WHITE}[{ts}] {code} đã quay lại Vùng A{Ansi.RESET}"
    if event_type == "LEFT_ZONE_B_UNVERIFIED":
        return f"{Ansi.RED}[{ts}] NGUY HIỂM: {code} đang rời khỏi Vùng B lớn (chưa xác minh){Ansi.RESET}"
    if event_type == "AUTO_RELEASE_ZONE_B_TIMEOUT":
        return f"{Ansi.WHITE}[{ts}] {code} đã xác minh và rời Vùng B > 30s -> tự động giải phóng mã{Ansi.RESET}"
    if event_type == "DELETED":
        return f"{Ansi.WHITE}[{ts}] Đã xóa thủ công thực thể {code}{Ansi.RESET}"
    return f"{Ansi.WHITE}[{ts}] {event_type}: {code}{Ansi.RESET}"


def format_escalation_line(level: int, key: str, codes: list, ts: str) -> str:
    codes_str = ", ".join(codes)
    if level == AlertLevel.HIGH_YELLOW:
        return f"{Ansi.YELLOW}{Ansi.BOLD}[{ts}] ⚠ MỨC 1 - BÁO ĐỘNG CAO: Toàn bộ nhóm/vùng [{key}] ({codes_str}) đã rời Vùng A!{Ansi.RESET}"
    if level == AlertLevel.CRITICAL_RED:
        return (f"{Ansi.RED_BOLD_BLINK}[{ts}] 🚨 MỨC 2 - NGUY CẤP: Toàn bộ nhóm/vùng [{key}] ({codes_str}) "
                f"đã rời cả Vùng B! 🚨{Ansi.RESET}")
    return ""
