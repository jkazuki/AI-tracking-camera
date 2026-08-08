"""
main.py
Điểm khởi chạy chính của hệ thống.

Luồng hoạt động:
  1. [Lần đầu chạy / hoặc gõ phím 'r'] Chọn 1 CỬA SỔ app camera đang mở (kiểu
     Window Capture của OBS), khoanh crop bỏ phần rác (toolbar, thanh chọn
     thiết bị...) bên trong cửa sổ đó -- hoặc khoanh 1 vùng màn hình cố định
     nếu không dùng chế độ cửa sổ -- để làm Composite Canvas (capture.py).
  2. [Lần đầu chạy / hoặc gõ phím 'e'] Vào chế độ vẽ vùng A/B/C bằng chuột
     (zone_editor.py). Vẽ Vùng A là TUỲ CHỌN -- không vẽ/gán Vùng A cũng
     không sao, thực thể vẫn quản lý được bình thường (chỉ không có cảnh
     báo "rời Vùng A").
  3. Vòng lặp chính: đọc canvas -> YOLOv8+ByteTrack (tracker.py) -> tính Foot
     Point -> kiểm tra Shapely polygon.contains() cho từng Vùng A/B/C ->
     nếu là track_id MỚI, thử RE-ID bằng khuôn mặt (reid.py) để nối lại vào
     thực thể cũ nếu ByteTrack vừa bị đứt track -> cập nhật trạng thái thực
     thể (state_manager.py, có lọc vật thể tĩnh) -> tính escalation
     (alerts.py) -> đẩy sự kiện lên CMD 1, hiển thị Bounding Box màu tương
     ứng lên canvas.
  4. CMD 1 (cmd1_console.py = Bảng thông báo, xác nhận Y/N) và CMD 2
     (cmd2_console.py = gán vùng/xác minh/biệt danh) chạy trên 2 thread song
     song, giao tiếp qua threading.Lock (state dùng chung) và queue.Queue
     (dòng sự kiện một chiều -> CMD1).

Chạy: python main.py
"""

import queue
import threading
import time

import cv2

import config
from capture import CompositeCanvas
from tracker import PersonTracker
from zone_editor import ZoneEditor
from state_manager import EntityManager, EntityState
from alerts import EscalationEngine
from geometry import point_in_polygon
from cmd1_console import run_notification_console
from cmd2_console import run_operator_console
from reid import FaceGallery, extract_face_embedding, HAS_FACE_RECOGNITION


def _fit_window(window_name: str, content_w: int, content_h: int, max_w: int = 1600, max_h: int = 900):
    """
    Tạo cửa sổ CÓ THỂ THU PHÓNG/DI CHUYỂN (WINDOW_NORMAL) và đặt kích thước
    ban đầu vừa với màn hình, để tránh tình trạng cửa sổ bị phóng lớn hơn màn
    hình thực tế (do DPI scaling) khiến không thấy được mép dưới/phải và
    không có thanh tiêu đề để kéo/resize lại.
    """
    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    scale = min(max_w / content_w, max_h / content_h, 1.0)
    cv2.resizeWindow(window_name, max(int(content_w * scale), 320), max(int(content_h * scale), 240))
    cv2.moveWindow(window_name, 30, 30)


def run_zone_setup(canvas: CompositeCanvas, editor: ZoneEditor):
    """Chế độ vẽ vùng tương tác trước khi bắt đầu giám sát. Vẽ Vùng A là TUỲ CHỌN."""
    _fit_window(config.WINDOW_NAME, config.CANVAS_WIDTH, config.CANVAS_HEIGHT)
    cv2.setMouseCallback(config.WINDOW_NAME, editor.on_mouse)
    print("\n=== CHẾ ĐỘ VẼ VÙNG ===")
    print("Nhấn giữ chuột trái và kéo để vẽ đa giác. Phím: a=Vùng A, b=Vùng B, c=Vùng C, z=undo, s=lưu, q=xong")
    print("(Vẽ Vùng A là TUỲ CHỌN -- có thể bỏ qua, không bắt buộc phải có)\n")

    while True:
        frame, _ = canvas.get_frame()
        frame = editor.draw_overlay(frame)
        cv2.putText(frame, f"Che do ve: Vung {editor.current_mode}  |  a/b/c doi vung, z=undo, s=luu, q=xong",
                    (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
        cv2.imshow(config.WINDOW_NAME, frame)
        key = cv2.waitKey(30)
        if key != -1:
            if not editor.handle_key(key):
                break
    editor.save()


def push_event(event_queue, kind, **kwargs):
    payload = {"kind": kind}
    payload.update(kwargs)
    event_queue.put(payload)


def main():
    canvas = CompositeCanvas().start()
    editor = ZoneEditor(config.CANVAS_WIDTH, config.CANVAS_HEIGHT)

    if not editor.load():
        print("Chưa có file zones.json -> vào chế độ vẽ vùng lần đầu.")
        run_zone_setup(canvas, editor)
    else:
        print("Đã tải vùng có sẵn. Nhấn 'e' trong lúc giám sát để vẽ/chỉnh sửa lại vùng.")

    event_queue = queue.Queue()
    state_lock = threading.Lock()
    stop_event = threading.Event()

    face_gallery = FaceGallery() if config.USE_FACE_REID else None
    if config.USE_FACE_REID and not HAS_FACE_RECOGNITION:
        print("[Lưu ý] Chưa cài `face_recognition` -> tắt tính năng Re-ID bằng khuôn mặt.")
        print("        Cài bằng: pip install face_recognition (cần dlib/cmake).")
        print("        Nếu không cài, track bị đứt (do khựng FPS...) sẽ tạo NEW_ID mới như trước.")

    def on_entity_event(event_type, entity, extra):
        push_event(event_queue, "entity_event", event_type=event_type, entity=entity, extra=extra)
        # Gỡ khỏi bộ nhớ Re-ID khi thực thể không còn được quản lý nữa
        if face_gallery is not None and event_type in ("DELETED", "AUTO_RELEASE_ZONE_B_TIMEOUT", "AUTO_REMOVED_STATIC_OBJECT"):
            face_gallery.forget(entity.display_id)

    entity_manager = EntityManager(on_event=on_entity_event)
    escalation_engine = EscalationEngine(entity_manager)

    try:
        tracker = PersonTracker()
    except Exception as ex:  # ultralytics/torch chưa cài hoặc GPU lỗi
        print(f"[LỖI] Không khởi tạo được YOLOv8 tracker: {ex}")
        print("Kiểm tra: pip install -r requirements.txt, driver GPU/CUDA, và config.DEVICE.")
        return

    # 2 thread song song: CMD1 = bảng thông báo, CMD2 = gán vùng/xác minh/biệt danh
    t1 = threading.Thread(target=run_notification_console, args=(event_queue, stop_event), daemon=True)
    t2 = threading.Thread(target=run_operator_console, args=(entity_manager, state_lock, stop_event), daemon=True)
    t1.start()
    t2.start()

    _fit_window(config.WINDOW_NAME, config.CANVAS_WIDTH, config.CANVAS_HEIGHT)
    zone_b_list = editor.zones_by_type("B")
    zone_a_list = editor.zones_by_type("A")
    zone_c_list = editor.zones_by_type("C")

    print("\n=== GIÁM SÁT ĐANG CHẠY === "
          "('e' = chỉnh vùng A/B/C, 'r' = chọn lại cửa sổ/vùng quay, 'q' = thoát)\n")

    try:
        while not stop_event.is_set():
            frame, _ = canvas.get_frame()
            detections = tracker.track(frame)

            with state_lock:
                for det in detections:
                    fx, fy = det.foot_point

                    in_zone_c = any(point_in_polygon((fx, fy), z.points) for z in zone_c_list)
                    in_zone_b = any(point_in_polygon((fx, fy), z.points) for z in zone_b_list)

                    # --- RE-ID bằng khuôn mặt: CHỈ chạy cho track_id CHƯA từng thấy,
                    #     để tránh tốn hiệu năng tính embedding mỗi frame cho mọi người ---
                    is_new_track = det.track_id not in entity_manager.entities
                    embedding = None
                    if is_new_track and face_gallery is not None:
                        embedding = extract_face_embedding(frame, (det.x1, det.y1, det.x2, det.y2))

                    matched_display_id = face_gallery.match(embedding) if (embedding is not None and face_gallery is not None) else None
                    if matched_display_id is not None:
                        e = entity_manager.reid_restore(matched_display_id, det.track_id)
                    else:
                        e = entity_manager.ensure_entity(det.track_id)

                    if is_new_track and embedding is not None and face_gallery is not None:
                        face_gallery.update(e.display_id, embedding)

                    # Vùng A là TUỲ CHỌN: chỉ kiểm tra nếu thực thể đã được gán vùng A
                    in_zone_a = False
                    if e.current_zone_a:
                        target_zone = next((z for z in zone_a_list if z.name == e.current_zone_a), None)
                        if target_zone:
                            in_zone_a = point_in_polygon((fx, fy), target_zone.points)

                    entity_manager.update_zone_membership(det.track_id, in_zone_a, in_zone_b, in_zone_c,
                                                           foot_point=(fx, fy))

                    # Thực thể có thể đã bị bộ lọc vật thể tĩnh tự xoá bên trong update_zone_membership
                    if det.track_id not in entity_manager.entities:
                        continue

                    color = entity_manager.get_color(e)
                    blink_on = (int(time.time() * 2) % 2 == 0)  # nháy 2 lần/giây cho Mức 2
                    thickness = 2
                    if e.state == EntityState.ALERT and e.left_zone_b_at is not None:
                        thickness = 4 if blink_on else 1

                    cv2.rectangle(frame, (int(det.x1), int(det.y1)), (int(det.x2), int(det.y2)), color, thickness)
                    cv2.circle(frame, (int(fx), int(fy)), 4, color, -1)
                    cv2.putText(frame, e.display_code, (int(det.x1), max(0, int(det.y1) - 8)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

                for ev in escalation_engine.evaluate():
                    push_event(event_queue, "escalation", level=ev["level"], key=ev["key"], codes=ev["codes"])

            frame = editor.draw_overlay(frame)
            cv2.imshow(config.WINDOW_NAME, frame)

            key = cv2.waitKey(1) & 0xFF
            if key == ord("q"):
                stop_event.set()
                break
            elif key == ord("e"):
                run_zone_setup(canvas, editor)
                zone_b_list = editor.zones_by_type("B")
                zone_a_list = editor.zones_by_type("A")
                zone_c_list = editor.zones_by_type("C")
            elif key == ord("r"):
                canvas.reselect_region()

    finally:
        stop_event.set()
        canvas.stop()
        cv2.destroyAllWindows()
        print("Đã dừng hệ thống giám sát.")


if __name__ == "__main__":
    main()
