"""
cmd1_console.py
Cửa sổ CMD 1: BẢNG THÔNG BÁO (Notification Inbox).

CMD 1 giờ CHỈ dùng để NHẬN & XÁC NHẬN thông báo cảnh báo -- không dùng để gõ
lệnh gán vùng/xác minh/biệt danh nữa (việc đó chuyển sang CMD 2, xem
cmd2_console.py).

Mỗi VẤN ĐỀ cảnh báo (theo entity + loại sự kiện, hoặc theo nhóm/vùng + mức
báo động) CHỈ được in ra 1 LẦN, sau đó bị khoá (không lặp lại liên tục mỗi
frame) cho tới khi được xác nhận bằng cách gõ:
  y   -> Đã xem (ghi nhận đã kiểm tra)
  n   -> Bỏ qua (huỷ thông báo đang chờ)
Cả 2 đều xoá HẾT các thông báo đang chờ hiện tại; nếu vấn đề còn tiếp diễn,
nó sẽ được báo lại (mới) ở lần cập nhật kế tiếp.

Các sự kiện thông tin thường (người mới vào, đã gán mã, đã xác minh...)
vẫn hiện ra bình thường nhưng KHÔNG cần xác nhận Y/N.
"""

import queue
import threading
import time

from alerts import format_log_line, format_escalation_line
from config import Ansi

HELP_TEXT = """
=== CMD 1: BẢNG THÔNG BÁO (chỉ nhận & xác nhận, không gõ lệnh gán vùng) ===
  Các cảnh báo QUAN TRỌNG (rời Vùng A, rời Vùng B, vào Vùng C, báo động
  Mức 1/Mức 2) chỉ hiện 1 lần và chờ xác nhận. Gõ:
    y   -> Đã xem (xác nhận đã kiểm tra)
    n   -> Bỏ qua (huỷ thông báo đang chờ)
  (Muốn gán vùng / xác minh / đặt biệt danh, gõ lệnh ở cửa sổ CMD 2)
=============================================================================
"""

# Các loại sự kiện được coi là "cảnh báo" cần xác nhận Y/N (chống lặp lại)
ALERT_EVENT_TYPES = {"ENTER_ZONE_C", "ALERT_LEFT_ZONE_A", "LEFT_ZONE_B_UNVERIFIED"}


def _event_key(item):
    """Khoá chống lặp: 1 vấn đề (entity+loại sự kiện, hoặc nhóm+mức) chỉ báo 1 lần cho tới khi xác nhận."""
    if item["kind"] == "entity_event":
        return ("entity_event", item["event_type"], item["entity"].track_id)
    if item["kind"] == "escalation":
        return ("escalation", item["level"], item["key"])
    return ("other", str(item))


def run_notification_console(event_queue: "queue.Queue", stop_event: threading.Event):
    print(HELP_TEXT)
    pending_keys = set()
    input_queue: "queue.Queue" = queue.Queue()

    def _input_reader():
        while not stop_event.is_set():
            try:
                raw = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                stop_event.set()
                break
            if raw:
                input_queue.put(raw)

    threading.Thread(target=_input_reader, daemon=True).start()

    while not stop_event.is_set():
        # --- Xử lý phím Y/N gõ vào: xoá hết thông báo đang chờ (báo lại nếu tái diễn) ---
        try:
            while True:
                raw = input_queue.get_nowait()
                if raw in ("y", "n"):
                    if pending_keys:
                        note = "Đã xem" if raw == "y" else "Đã bỏ qua"
                        print(f"{Ansi.WHITE}[{note}] {len(pending_keys)} thông báo đang chờ đã được xử lý.{Ansi.RESET}")
                        pending_keys.clear()
                    else:
                        print(f"{Ansi.WHITE}(Không có thông báo nào đang chờ){Ansi.RESET}")
                elif raw in ("help", "?"):
                    print(HELP_TEXT)
                else:
                    print("Gõ 'y' (đã xem) hoặc 'n' (bỏ qua).")
        except queue.Empty:
            pass

        # --- Lấy sự kiện mới từ hàng đợi ---
        try:
            item = event_queue.get(timeout=0.3)
        except queue.Empty:
            continue

        ts = time.strftime("%H:%M:%S")
        needs_ack = False

        if item["kind"] == "entity_event":
            event_type = item["event_type"]
            line = format_log_line(event_type, item["entity"], {"timestamp_str": ts})
            needs_ack = event_type in ALERT_EVENT_TYPES
        elif item["kind"] == "escalation":
            line = format_escalation_line(item["level"], item["key"], item["codes"], ts)
            needs_ack = True
        else:
            line = ""

        if not line:
            continue

        if not needs_ack:
            print(line)  # thông tin thường -- không cần xác nhận, không chống lặp
            continue

        key = _event_key(item)
        if key in pending_keys:
            continue  # đã báo rồi, đang chờ xác nhận -> không lặp lại
        pending_keys.add(key)
        print(line)
        print(f"{Ansi.WHITE}      -> gõ 'y' (đã xem) hoặc 'n' (bỏ qua){Ansi.RESET}")
