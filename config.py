"""
config.py
Cấu hình trung tâm cho hệ thống giám sát đa camera.
Chỉnh sửa các giá trị bên dưới cho đúng với môi trường triển khai thực tế.
"""

import os

# ------------------------------------------------------------------
# 1. VÙNG CHỤP: THEO CỬA SỔ (kiểu OBS) hoặc THEO VÙNG MÀN HÌNH
# ------------------------------------------------------------------
# Không cần IP camera / RTSP nữa. Chương trình chụp trực tiếp từ PC, có 2 chế độ:
#   - "window" (khuyến nghị): chọn ĐÚNG 1 CỬA SỔ/TAB app camera đang mở
#     (giống "Window Capture" của OBS), sau đó khoanh thêm 1 vùng bên trong
#     cửa sổ đó để CẮT BỎ phần rác (thanh chọn thiết bị, toolbar, viền app...).
#     Capture sẽ tự bám theo cửa sổ nếu bạn di chuyển nó. Cần cài `pywin32`
#     và chỉ chạy được trên Windows.
#   - "screen": khoanh 1 vùng cố định trên màn hình (chế độ cũ), dùng khi
#     không có pywin32 hoặc không phải Windows.
# Chế độ thực tế được lưu kèm trong screen_region.json sau khi bạn chọn.
PREFER_WINDOW_CAPTURE = True   # Ưu tiên hỏi chọn cửa sổ trước (nếu máy hỗ trợ pywin32)

# Chụp NỘI DUNG cửa sổ bằng Windows Graphics Capture API (thư viện `windows-capture`)
# thay vì đọc pixel màn hình (mss). Đây là cách BẮT BUỘC để tránh hiện tượng
# "lặp màn hình" (feedback loop / hall of mirrors) khi cửa sổ xem trực tiếp của
# chương trình đè lên đúng vùng đang chụp. Cần cài: pip install windows-capture
USE_WGC_FOR_WINDOW_CAPTURE = True

SCREEN_REGION_SAVE_PATH = os.path.join(os.path.dirname(__file__), "screen_region.json")

CAPTURE_FPS_LIMIT = 30           # Giới hạn số khung hình chụp mỗi giây (giảm tải CPU)
CAPTURE_MONITOR_INDEX = 1        # Dùng ở chế độ "screen": 0 = gộp mọi màn hình, 1 = màn hình chính, 2 = màn hình phụ...
WINDOW_REFRESH_INTERVAL_SEC = 1.0  # Chế độ "window": chu kỳ kiểm tra lại vị trí cửa sổ (để bám theo khi bị di chuyển)

# ------------------------------------------------------------------
# 2. KÍCH THƯỚC XỬ LÝ / HIỂN THỊ (Canvas)
# ------------------------------------------------------------------
# Vùng màn hình chụp được (kích thước bất kỳ do bạn kéo chuột) sẽ được
# resize về đúng kích thước này trước khi đưa vào YOLOv8 và hiển thị.
CANVAS_WIDTH = 1920
CANVAS_HEIGHT = 1080

WINDOW_NAME = "Composite Canvas - AI Surveillance"

# ------------------------------------------------------------------
# 3. MÔ HÌNH AI (YOLOv8 + ByteTrack)
# ------------------------------------------------------------------
YOLO_MODEL_PATH = "yolov8n.pt"    # Đổi sang yolov8s.pt/yolov8m.pt nếu cần độ chính xác cao hơn
YOLO_CONFIDENCE_THRESHOLD = 0.4
YOLO_TARGET_CLASSES = [0]         # class 0 = "person" trong COCO dataset
TRACKER_CONFIG = "bytetrack.yaml" # File cấu hình tracker built-in của ultralytics
DEVICE = "cuda:0"                 # Đổi thành "cpu" nếu không có GPU

# ------------------------------------------------------------------
# 4. NGƯỠNG THỜI GIAN & LOGIC NGHIỆP VỤ
# ------------------------------------------------------------------
ALERT_GRACE_PERIOD_SEC = 1.0      # Thời gian "ân hạn" trước khi báo động Vùng A (Trạng thái 4)
ZONE_B_RELEASE_TIMEOUT_SEC = 30.0 # Thời gian T: tự động giải phóng mã ID khi rời Vùng B

# ------------------------------------------------------------------
# 5. FILE LƯU TRỮ VÙNG (ZONES) - để không phải vẽ lại mỗi lần chạy
# ------------------------------------------------------------------
ZONES_SAVE_PATH = os.path.join(os.path.dirname(__file__), "zones.json")

# ------------------------------------------------------------------
# 6. MÀU SẮC (BGR cho OpenCV)
# ------------------------------------------------------------------
COLOR_WHITE = (255, 255, 255)
COLOR_YELLOW = (0, 255, 255)
COLOR_GREEN = (0, 200, 0)
COLOR_RED = (0, 0, 255)
COLOR_ORANGE = (0, 140, 255)
COLOR_CYAN = (255, 255, 0)

ZONE_COLOR_A = (255, 200, 0)   # Sub-Zone
ZONE_COLOR_B = (200, 0, 200)   # Master Zone
ZONE_COLOR_C = (0, 0, 255)     # Restricted Zone

# ------------------------------------------------------------------
# 7. ANSI ESCAPE CODES cho CMD 1 (Bảng thông báo)
# ------------------------------------------------------------------
class Ansi:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    BLINK = "\033[5m"
    WHITE = "\033[97m"
    YELLOW = "\033[93m"
    ORANGE = "\033[38;5;208m"
    CYAN = "\033[96m"
    RED = "\033[91m"
    RED_BOLD_BLINK = "\033[1m\033[5m\033[91m"

# ------------------------------------------------------------------
# 8. RE-ID BẰNG KHUÔN MẶT (giữ nguyên ID khi ByteTrack bị đứt track)
# ------------------------------------------------------------------
# Khi camera bị khựng FPS / thực thể bị che khuất rồi xuất hiện lại, ByteTrack
# thường cấp 1 track_id MỚI cho cùng 1 người. Để tránh phải gán lại từ đầu,
# hệ thống so khớp khuôn mặt của track_id mới với các thực thể đã biết gần
# đây -- nếu khớp, NỐI LẠI vào đúng thực thể cũ (giữ nguyên ID/vùng/biệt
# danh/trạng thái xác minh) thay vì tạo NEW_ID mới. Cần: pip install face_recognition
USE_FACE_REID = True
REID_MATCH_THRESHOLD = 0.55        # Khoảng cách embedding tối đa để coi là cùng 1 người (thấp hơn = khắt khe hơn)
REID_MAX_SAMPLES_PER_ENTITY = 5    # Số mẫu embedding gần nhất lưu mỗi người (khớp tốt hơn theo góc mặt/ánh sáng)
REID_GALLERY_TTL_SEC = 300.0       # Không thấy lại sau chừng này giây -> xoá khỏi bộ nhớ Re-ID (rời hẳn khu vực)

# ------------------------------------------------------------------
# 9. LỌC VẬT THỂ TĨNH (giảm báo động giả khi YOLOv8 nhận nhầm đồ vật thành người)
# ------------------------------------------------------------------
# Chỉ áp dụng cho thực thể CHƯA được gán vùng/xác minh/đặt biệt danh gì cả:
# nếu vị trí gần như không đổi trong 1 khoảng thời gian dài -> khả năng cao là
# đồ vật tĩnh bị nhận nhầm thành người -> tự động loại bỏ khỏi danh sách.
STATIC_OBJECT_FILTER_ENABLED = True
STATIC_OBJECT_WINDOW_SEC = 10.0     # Cửa sổ thời gian xét độ "đứng yên"
STATIC_OBJECT_MOVEMENT_PX = 12.0    # Foot Point di chuyển dưới ngưỡng này (pixel) coi là không di chuyển
STATIC_OBJECT_CONFIRM_SEC = 15.0    # Phải đứng yên liên tục ít nhất chừng này giây mới tự động loại bỏ
