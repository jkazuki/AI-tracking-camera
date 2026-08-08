"""
cmd2_console.py
Cửa sổ CMD 2: GÁN VÙNG / XÁC MINH / BIỆT DANH (Operator Console).

Chạy trên 1 thread riêng (blocking input()), giao tiếp với vòng lặp xử lý
video chính qua threading.Lock bảo vệ EntityManager dùng chung.

Chương trình TỰ ĐỘNG đặt track_id (nội bộ) và 1 "ID hiển thị" đơn giản
(1, 2, 3...) cho mỗi người mới xuất hiện -- xem thông báo bên CMD1 dạng
"NEW_ID:<số>".

CÚ PHÁP NHANH (khuyến nghị) -- tất cả đều TUỲ CHỌN trừ ID, chỉ cần gõ ít
nhất 1 trong 3 (vùng / xác minh / biệt danh), KHÔNG bắt buộc phải có vùng A:
    <ID>[-<mã vùng>][.Y][/<biệt danh>]

Ví dụ:
    1-A1        gán người số 1 vào vùng A1 (không xác minh, không biệt danh)
    1.Y         chỉ xác minh AN TOÀN cho người số 1 (không cần vùng)
    1/Kz        chỉ đặt biệt danh 'Kz' cho người số 1 (không cần vùng)
    1-A1.Y      gán vùng A1 + xác minh cùng lúc
    1-A1/Kz     gán vùng A1 + đặt biệt danh cùng lúc
    1-A1.Y/Kz   gán vùng A1 + xác minh + biệt danh cùng lúc

Ngoài ra vẫn hỗ trợ các lệnh đầy đủ (dùng khi cần nhóm G1, G2... hoặc thao
tác trực tiếp bằng track_id nội bộ):
  bind <track_id> <mã_Ax-y> [mã_nhóm]   vd: bind 102 A1-1 G1
  del <ID hoặc mã_Ax-y>                  vd: del 1   hoặc   del A1-1
  list                                    Liệt kê toàn bộ thực thể đang quản lý
  help                                    Hiển thị lại danh sách lệnh
  exit                                    Thoát chương trình
"""

import re
import threading


HELP_TEXT = """
=== CMD 2: GÁN VÙNG / XÁC MINH / BIỆT DANH ===
  Cú pháp nhanh (tuỳ chọn, không bắt buộc phải có vùng A):
      <ID>[-<mã vùng>][.Y][/<biệt danh>]
    vd:  1-A1     1.Y     1/Kz     1-A1.Y     1-A1/Kz     1-A1.Y/Kz
  ---------------------------------------------------------------
  bind <track_id> <mã_Ax-y> [mã_nhóm]   vd: bind 102 A1-1 G1  (dạng đầy đủ, hỗ trợ nhóm)
  del <ID hoặc mã>                       vd: del 1   hoặc   del A1-1
  list                                   liệt kê thực thể đang quản lý
  help                                   hiển thị lại trợ giúp này
  exit                                   thoát chương trình
========================================
"""

# Cú pháp nhanh: "<id>[-<vùng>][.Y][/<biệt danh>]" -- tất cả phần sau id đều tuỳ chọn
ASSIGN_RE = re.compile(
    r"^(?P<id>\d+)"
    r"(?:-(?P<zone>[A-Za-z]+\d+))?"
    r"(?:\.(?P<verify>[Yy]))?"
    r"(?:/(?P<nickname>.+))?$"
)


def run_operator_console(entity_manager, state_lock: threading.Lock, stop_event: threading.Event):
    print(HELP_TEXT)
    while not stop_event.is_set():
        try:
            raw = input("CMD2> ").strip()
        except (EOFError, KeyboardInterrupt):
            stop_event.set()
            break
        if not raw:
            continue

        # --- Cú pháp nhanh: "1-A1", "1.Y", "1/Kz", "1-A1.Y", "1-A1/Kz", ... ---
        m = ASSIGN_RE.match(raw)
        if m:
            display_id = int(m.group("id"))
            zone_code = m.group("zone")
            verified = bool(m.group("verify"))
            nickname = m.group("nickname")

            if not (zone_code or verified or nickname):
                print("Cần ít nhất 1 thông tin: vùng (-A1), xác minh (.Y), hoặc biệt danh (/tên).")
                continue

            with state_lock:
                ok = entity_manager.assign_by_display_id(
                    display_id, zone_code=zone_code, verified=verified, nickname=nickname
                )
            if ok:
                parts = []
                if zone_code:
                    parts.append(f"vùng {zone_code}")
                if verified:
                    parts.append("đã XÁC MINH")
                if nickname:
                    parts.append(f"biệt danh '{nickname}'")
                print(f"Đã cập nhật người số {display_id}: {', '.join(parts)}")
            else:
                print(f"Lỗi: không tìm thấy ID hiển thị số {display_id} (gõ 'list' để xem danh sách)")
            continue

        parts = raw.split()
        cmd = parts[0].lower()

        with state_lock:
            if cmd == "bind" and len(parts) >= 3:
                try:
                    track_id = int(parts[1])
                except ValueError:
                    print("Lỗi: track_id phải là số nguyên.")
                    continue
                code = parts[2]
                group_id = parts[3] if len(parts) > 3 else None
                ok = entity_manager.bind(track_id, code, group_id)
                print(f"{'Đã gán' if ok else 'Lỗi: track_id không tồn tại'} {code} <- track_id {track_id}")

            elif cmd == "list":
                entities = entity_manager.list_entities()
                if not entities:
                    print("(Không có thực thể nào đang được quản lý)")
                for e in entities:
                    print(f"  ID={e.display_id:<4} track_id={e.track_id:<6} code={e.display_code:<15} "
                          f"state={e.state.value:<12} zoneA={e.current_zone_a} zoneC={e.in_zone_c}")

            elif cmd == "del" and len(parts) == 2:
                target = parts[1]
                if target.isdigit():
                    ok = entity_manager.delete_by_display_id(int(target))
                else:
                    ok = entity_manager.delete_by_code(target)
                print(f"{'Đã xóa' if ok else 'Lỗi: không tìm thấy'} {target}")

            elif cmd == "help":
                print(HELP_TEXT)

            elif cmd == "exit":
                stop_event.set()
                print("Đang thoát chương trình...")

            else:
                print("Lệnh không hợp lệ. Gõ 'help' để xem danh sách lệnh, "
                      "hoặc gõ nhanh kiểu '1-A1', '1.Y', '1/Kz'.")
