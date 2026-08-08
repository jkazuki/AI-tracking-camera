"""
capture.py
2 chế độ:

  - "window" (khuyến nghị, giống Window Capture của OBS): chọn ĐÚNG 1 cửa sổ
    app camera đang mở (vd Imou Life), rồi khoanh thêm 1 vùng BÊN TRONG cửa
    sổ đó để cắt bỏ phần rác (thanh chọn thiết bị, toolbar, viền cửa sổ...).
    Capture tự bám theo cửa sổ nếu bạn kéo di chuyển nó. Cần cài `pywin32`,
    chỉ chạy trên Windows.
  - "screen": khoanh 1 vùng cố định trên màn hình (không bám theo cửa sổ nào
    cả). Dùng khi không có pywin32 / không phải Windows.

Cả 2 chế độ đều cho ra 1 Composite Canvas duy nhất để main.py xử lý tiếp
(YOLOv8 + Zone A/B/C) mà không cần đổi logic phía sau.
"""

import json
import threading
import time

import cv2
import numpy as np
import mss

import config

try:
    import win32gui
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

try:
    from windows_capture import WindowsCapture as _WgcWindowsCapture
    HAS_WGC = True
except ImportError:
    HAS_WGC = False


# =====================================================================
# Chọn vùng bằng cách kéo chuột trên 1 tấm ảnh cho sẵn (dùng chung cho
# cả 2 chế độ: crop trong cửa sổ, hoặc khoanh vùng trên toàn màn hình).
# ====================================================================
def _fit_window(win_name: str, img_w: int, img_h: int, max_w: int = 1600, max_h: int = 900):
    """
    Đặt kích thước cửa sổ vừa với màn hình (tránh bị phóng lớn hơn màn hình
    thực tế do DPI scaling, khiến không thấy được mép dưới/phải và không có
    thanh tiêu đề để kéo/resize lại). Cửa sổ vẫn có thể được người dùng kéo
    to/nhỏ lại thoải mái vì đã tạo với cv2.WINDOW_NORMAL.
    """
    scale = min(max_w / img_w, max_h / img_h, 1.0)
    cv2.resizeWindow(win_name, max(int(img_w * scale), 320), max(int(img_h * scale), 240))
    cv2.moveWindow(win_name, 30, 30)


def _pick_rect_from_image(img, win_name: str):
    """
    Hiện `img` lên 1 cửa sổ OpenCV, cho người dùng kéo chuột khoanh 1 hình
    chữ nhật. Enter = xác nhận, r = chọn lại, q/ESC = huỷ.
    Trả về (x, y, w, h) theo toạ độ trong `img`, hoặc None nếu huỷ.
    """
    state = {"start": None, "end": None, "drawing": False}

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            state["drawing"] = True
            state["start"] = (x, y)
            state["end"] = (x, y)
        elif event == cv2.EVENT_MOUSEMOVE and state["drawing"]:
            state["end"] = (x, y)
        elif event == cv2.EVENT_LBUTTONUP:
            state["drawing"] = False
            state["end"] = (x, y)

    cv2.namedWindow(win_name, cv2.WINDOW_NORMAL)
    h, w = img.shape[:2]
    _fit_window(win_name, w, h)
    cv2.setMouseCallback(win_name, on_mouse)

    rect = None
    while True:
        disp = img.copy()
        if state["start"] and state["end"]:
            cv2.rectangle(disp, state["start"], state["end"], (0, 255, 0), 2)
        cv2.imshow(win_name, disp)
        key = cv2.waitKey(30) & 0xFF
        if key in (13, 10):  # Enter
            if state["start"] and state["end"]:
                x1, y1 = state["start"]
                x2, y2 = state["end"]
                x, y = min(x1, x2), min(y1, y2)
                w, h = abs(x2 - x1), abs(y2 - y1)
                if w > 10 and h > 10:
                    rect = (x, y, w, h)
                    break
                print("Vùng chọn quá nhỏ, hãy kéo lại.")
        elif key == ord("r"):
            state["start"] = None
            state["end"] = None
        elif key in (27, ord("q")):
            break

    cv2.destroyWindow(win_name)
    return rect


# =====================================================================
# Chế độ "window": liệt kê cửa sổ đang mở, giống danh sách nguồn Windoww
# Capture của OBS.
# =====================================================================
def list_windows():
    """Trả về list[(hwnd, title, rect)] các cửa sổ đang hiển thị, có tiêu đề, đủ lớn."""
    windows = []

    def _enum_handler(hwnd, _ctx):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd).strip()
        if not title:
            return
        left, top, right, bottom = win32gui.GetWindowRect(hwnd)
        if (right - left) > 50 and (bottom - top) > 50:
            windows.append((hwnd, title, (left, top, right, bottom)))

    win32gui.EnumWindows(_enum_handler, None)
    return windows


def _select_window_source():
    """Cho người dùng chọn 1 cửa sổ từ danh sách, rồi khoanh vùng crop bên trong nó."""
    windows = list_windows()
    if not windows:
        print("Không tìm thấy cửa sổ nào đang mở. Chuyển sang chế độ chọn vùng màn hình.")
        return None

    print("\n=== CHỌN CỬA SỔ CẦN QUAY (giống Window Capture của OBS) ===")
    print("  0) Không dùng cửa sổ nào -- chọn 1 vùng màn hình cố định thay thế")
    for i, (_hwnd, title, _rect) in enumerate(windows, start=1):
        print(f"  {i}) {title}")

    try:
        choice = int(input("Nhập số thứ tự cửa sổ cần quay: ").strip())
    except (ValueError, EOFError):
        return None
    if choice == 0 or choice < 0 or choice > len(windows):
        return None

    hwnd, title, rect = windows[choice - 1]
    try:
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.3)
    except Exception:
        pass  

    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    win_w, win_h = right - left, bottom - top
    with mss.mss() as sct:
        raw = np.array(sct.grab({"left": left, "top": top, "width": win_w, "height": win_h}))
    win_img = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)

    print(f"\nĐã chọn cửa sổ: '{title}'")
    print("Kéo chuột khoanh ĐÚNG phần hình ảnh camera bên trong cửa sổ này")
    print("(bỏ ra ngoài các phần rác như thanh chọn thiết bị, toolbar, viền app).")
    print("Enter = xác nhận | r = chọn lại | q/ESC = huỷ\n")

    crop = _pick_rect_from_image(win_img, f"Khoanh vung trong '{title}' (Enter=OK, r=chon lai, q=huy)")
    if crop is None:
        return None
    cx, cy, cw, ch = crop
    return {
        "mode": "window",
        "window_title": title,
        "crop_left": cx,
        "crop_top": cy,
        "crop_width": cw,
        "crop_height": ch,
    }


# =====================================================================
# Chế độ "screen": khoanh 1 vùng cố định trên toàn màn hình (chế độ cũ)
# =====================================================================
def _select_screen_source():
    with mss.mss() as sct:
        monitor = sct.monitors[config.CAPTURE_MONITOR_INDEX]
        raw = np.array(sct.grab(monitor))
    full_img = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)

    print("\n=== CHỌN VÙNG MÀN HÌNH CẦN GIÁM SÁT ===")
    print("Kéo giữ chuột trái khoanh đúng khung hình camera đang hiển thị.")
    print("Enter = xác nhận | r = chọn lại | q/ESC = huỷ\n")

    rect = _pick_rect_from_image(full_img, "Chon vung man hinh (Enter=OK, r=chon lai, q=huy)")
    if rect is None:
        return None
    x, y, w, h = rect
    return {
        "mode": "screen",
        "left": monitor["left"] + x,
        "top": monitor["top"] + y,
        "width": w,
        "height": h,
        "monitor": config.CAPTURE_MONITOR_INDEX,
    }


def select_capture_source():
    """
    Điểm vào chính để chọn nguồn quay: ưu tiên chọn theo CỬA SỔ (kiểu OBS)
    nếu máy có pywin32, ngược lại (hoặc người dùng bấm 0/huỷ) sẽ hỏi chọn
    theo VÙNG MÀN HÌNH cố định.
    """
    region = None
    if HAS_WIN32 and config.PREFER_WINDOW_CAPTURE:
        region = _select_window_source()
    elif not HAS_WIN32:
        print("[Lưu ý] Chưa cài `pywin32` nên không thể chọn theo cửa sổ (kiểu OBS).")
        print("         Cài bằng lệnh: pip install pywin32  (chỉ hỗ trợ Windows)")

    if region is None:
        region = _select_screen_source()
    if region is None:
        raise RuntimeError(
            "Chưa chọn được nguồn quay nào. Hãy chạy lại, mở sẵn app camera "
            "trên PC, rồi chọn cửa sổ hoặc khoanh vùng màn hình cần giám sát."
        )
    return region


def load_region(path=None):
    path = path or config.SCREEN_REGION_SAVE_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def save_region(region: dict, path=None):
    path = path or config.SCREEN_REGION_SAVE_PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(region, f, ensure_ascii=False, indent=2)
    print(f"[Capture] Đã lưu cấu hình nguồn quay ({region.get('mode')}) vào {path}")


# =====================================================================
# Luồng đọc nền (threaded), luôn giữ khung hình mới nhất để giảm độ trễ
# =====================================================================
class ScreenCapture:
    """Chế độ 'screen': chụp liên tục 1 vùng màn hình cố định."""

    def __init__(self, region: dict):
        self.region = region
        self.frame = None
        self.lock = threading.Lock()
        self.running = False
        self.connected = False
        self.thread = None

    def start(self):
        self.running = True
        self.thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.thread.start()
        return self

    def _reader_loop(self):
        delay = 1.0 / max(config.CAPTURE_FPS_LIMIT, 1)
        with mss.mss() as sct:
            self.connected = True
            while self.running:
                t0 = time.time()
                try:
                    raw = np.array(sct.grab(self.region))
                    frame = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
                    with self.lock:
                        self.frame = frame
                    self.connected = True
                except Exception as ex:
                    self.connected = False
                    print(f"[ScreenCapture] Lỗi chụp màn hình: {ex}")
                elapsed = time.time() - t0
                if elapsed < delay:
                    time.sleep(delay - elapsed)

    def read(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)


class _LegacyPollingWindowCapture:
    """
    [DỰ PHÒNG - có thể gây LẶP MÀN HÌNH] Bám theo 1 cửa sổ bằng cách đọc lại
    pixel màn hình (mss) tại toạ độ cửa sổ đó theo chu kỳ. Vì đây là đọc PIXEL
    MÀN HÌNH THỰC TẾ (không phải nội dung riêng của cửa sổ), nếu cửa sổ xem
    trực tiếp (preview) của chương trình đè lên đúng vùng đang chụp, mỗi khung
    hình mới sẽ vô tình chụp luôn khung hình cũ vừa hiển thị -> hiện tượng ảnh
    lặp/lồng vào nhau liên tục (feedback loop).
    Chỉ dùng lớp này khi KHÔNG cài được `windows-capture` (xem WgcWindowCapture).
    Nếu buộc phải dùng, hãy đặt cửa sổ preview của chương trình ở màn hình
    khác hoặc góc không đè lên cửa sổ camera.
    """

    def __init__(self, region: dict):
        self.window_title = region["window_title"]
        self.crop = (region["crop_left"], region["crop_top"], region["crop_width"], region["crop_height"])
        self.frame = None
        self.lock = threading.Lock()
        self.running = False
        self.connected = False
        self.thread = None
        self._hwnd = None
        self._last_locate = 0.0

    def _locate_window(self):
        if not HAS_WIN32:
            return None
        found = {"hwnd": None}

        def _enum_handler(hwnd, _ctx):
            if found["hwnd"] is not None:
                return
            if win32gui.IsWindowVisible(hwnd) and self.window_title in win32gui.GetWindowText(hwnd):
                found["hwnd"] = hwnd

        win32gui.EnumWindows(_enum_handler, None)
        return found["hwnd"]

    def start(self):
        if not HAS_WIN32:
            raise RuntimeError(
                "Nguồn quay đã lưu ở chế độ 'window' nhưng máy chưa cài pywin32. "
                "Cài bằng: pip install pywin32 (chỉ hỗ trợ Windows), hoặc xoá "
                "screen_region.json để chọn lại theo vùng màn hình."
            )
        print("[CẢNH BÁO] Đang dùng chế độ chụp cửa sổ DỰ PHÒNG (đọc pixel màn hình).")
        print("           Nếu thấy hình ảnh bị lặp/lồng vào nhau liên tục, hãy:")
        print("           1) Cài `pip install windows-capture` rồi chạy lại (khuyến nghị), hoặc")
        print("           2) Kéo cửa sổ xem trực tiếp của chương trình ra chỗ KHÔNG đè")
        print("              lên cửa sổ camera (hoặc dùng 2 màn hình).")
        self.running = True
        self.thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.thread.start()
        return self

    def _reader_loop(self):
        delay = 1.0 / max(config.CAPTURE_FPS_LIMIT, 1)
        cx, cy, cw, ch = self.crop
        with mss.mss() as sct:
            while self.running:
                t0 = time.time()
                now = t0
                if self._hwnd is None or (now - self._last_locate) > config.WINDOW_REFRESH_INTERVAL_SEC:
                    self._hwnd = self._locate_window()
                    self._last_locate = now

                if self._hwnd is None or not win32gui.IsWindow(self._hwnd):
                    self.connected = False
                    time.sleep(0.5)
                    continue

                try:
                    left, top, _right, _bottom = win32gui.GetWindowRect(self._hwnd)
                    region = {"left": left + cx, "top": top + cy, "width": cw, "height": ch}
                    raw = np.array(sct.grab(region))
                    frame = cv2.cvtColor(raw, cv2.COLOR_BGRA2BGR)
                    with self.lock:
                        self.frame = frame
                    self.connected = True
                except Exception as ex:
                    self.connected = False
                    print(f"[WindowCapture] Lỗi chụp cửa sổ '{self.window_title}': {ex}")

                elapsed = time.time() - t0
                if elapsed < delay:
                    time.sleep(delay - elapsed)

    def read(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)


class WgcWindowCapture:
    """
    Bám và chụp NỘI DUNG cửa sổ bằng Windows Graphics Capture API (thư viện
    `windows-capture`) -- đọc thẳng bộ đệm khung hình của chính cửa sổ nguồn,
    KHÔNG đọc pixel màn hình. Nhờ vậy dù cửa sổ xem trực tiếp (preview) của
    chương trình có đè lên cửa sổ camera hay không, hình ảnh vẫn KHÔNG bị lặp
    hay lồng vào nhau -- đây là cách OBS thật sự dùng cho "Window Capture".
    Cần cài: pip install windows-capture (chỉ hỗ trợ Windows 10/11).
    """

    def __init__(self, region: dict):
        self.window_title = region["window_title"]
        self.crop = (region["crop_left"], region["crop_top"], region["crop_width"], region["crop_height"])
        self.frame = None
        self.lock = threading.Lock()
        self.running = False
        self.connected = False
        self._stop_requested = False
        self._capture = None

    def start(self):
        if not HAS_WGC:
            raise RuntimeError(
                "Chưa cài `windows-capture`. Cài bằng: pip install windows-capture"
            )

        capture = _WgcWindowsCapture(window_name=self.window_title)
        cx, cy, cw, ch = self.crop

        @capture.event
        def on_frame_arrived(frame, capture_control):
            if self._stop_requested:
                capture_control.stop()
                return
            try:
                buf = frame.frame_buffer  # numpy BGRA, shape (H, W, 4)
                cropped = buf[cy:cy + ch, cx:cx + cw]
                bgr = cv2.cvtColor(cropped, cv2.COLOR_BGRA2BGR)
                with self.lock:
                    self.frame = bgr
                self.connected = True
            except Exception as ex:
                print(f"[WgcWindowCapture] Lỗi xử lý khung hình '{self.window_title}': {ex}")

        @capture.event
        def on_closed():
            self.connected = False

        self._capture = capture
        self.running = True
        self.connected = True
        try:
            self._capture.start_free_threaded()
        except Exception as ex:
            self.connected = False
            raise RuntimeError(f"Không khởi động được Windows Graphics Capture: {ex}") from ex
        return self

    def read(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def stop(self):
        self.running = False
        self._stop_requested = True

class CompositeCanvas:
    """
    Giữ nguyên tên lớp & giao diện (start/get_frame/stop) như bản RTSP cũ để
    main.py không cần sửa nhiều. Nguồn khung hình giờ là 1 cửa sổ (mode=
    "window", kiểu OBS, ưu tiên dùng Windows Graphics Capture) hoặc 1 vùng
    màn hình cố định (mode="screen").
    """

    def __init__(self, region: dict = None):
        region = region or load_region()
        if region is None:
            region = select_capture_source()
            save_region(region)

        self.region = region
        self.stream = self._build_stream(region)

        self.width = config.CANVAS_WIDTH
        self.height = config.CANVAS_HEIGHT

    @staticmethod
    def _build_stream(region: dict):
        if region.get("mode") == "window":
            if config.USE_WGC_FOR_WINDOW_CAPTURE and HAS_WGC:
                return WgcWindowCapture(region)
            if not HAS_WGC:
                print("[Lưu ý] Chưa cài `windows-capture` -> dùng chế độ chụp cửa sổ DỰ PHÒNG,")
                print("        có thể gây LẶP MÀN HÌNH nếu cửa sổ xem trực tiếp đè lên cửa sổ camera.")
                print("        Khuyến nghị: pip install windows-capture")
            return _LegacyPollingWindowCapture(region)
        return ScreenCapture(region)

    def start(self):
        self.stream.start()
        return self

    def get_frame(self):
        """Trả về (canvas_bgr, per_cam_frames_list) để tương thích chữ ký cũ."""
        frame = self.stream.read()
        if frame is None:
            frame = self._placeholder()
        else:
            frame = cv2.resize(frame, (self.width, self.height))
        return frame, [frame]

    def _placeholder(self):
        img = np.full((self.height, self.width, 3), 30, dtype=np.uint8)
        msg = "Dang cho khung hinh..." if self.stream.connected else "Mat ket noi nguon quay, dang thu lai..."
        cv2.putText(img, msg, (20, self.height // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2)
        return img

    def cam_offset_for_x(self, global_x: float) -> int:
        """Giữ lại để tương thích ngược; không còn nhiều camera nên luôn = 0."""
        return 0

    def reselect_region(self):
        """Chọn lại nguồn quay lúc đang chạy (đổi cửa sổ khác, hoặc khoanh lại vùng)."""
        self.stream.stop()
        region = select_capture_source()
        save_region(region)
        self.region = region
        self.stream = self._build_stream(region)
        self.stream.start()

    def stop(self):
        self.stream.stop()
