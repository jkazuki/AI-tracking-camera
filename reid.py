"""
reid.py
RE-ID (nhận diện lại) dựa trên khuôn mặt để GIỮ NGUYÊN ID/vùng/biệt danh/
trạng thái xác minh của 1 người khi ByteTrack bị ĐỨT TRACK (do FPS khựng,
bị che khuất, đi ra rồi vào lại khung hình, hoặc đổi giữa 3 camera ở 3 vị
trí khác nhau) và cấp 1 track_id MỚI cho cùng 1 người.

Vì sao dùng khuôn mặt thay vì đặc trưng ngoại hình (áo quần, dáng người)?
Ngoại hình dễ trùng nhau (nhiều người mặc đồ giống nhau) và thay đổi nhiều
giữa các góc camera khác nhau; khuôn mặt ổn định hơn nhiều và phù hợp khi hệ
thống dùng 3 camera đặt ở 3 vị trí khác nhau (góc nhìn khác nhau).

Cần cài: pip install face_recognition
(thư viện này dựa trên dlib -- trên Windows có thể cần cài thêm CMake và
Visual Studio Build Tools trước khi `pip install face_recognition` chạy được).

CHỈ chạy nhận diện khuôn mặt cho TRACK_ID MỚI xuất hiện (không chạy mỗi
frame cho track đã ổn định) để tiết kiệm hiệu năng -- xem cách gọi trong
main.py.
"""

import time

import numpy as np

import config

try:
    import face_recognition
    HAS_FACE_RECOGNITION = True
except ImportError:
    HAS_FACE_RECOGNITION = False


class FaceGallery:
    """
    Lưu embedding khuôn mặt (128 chiều) của từng thực thể theo display_id
    (ID hiển thị ổn định lâu dài), để so khớp khi có track_id mới xuất hiện.
    """

    def __init__(self):
        self.embeddings: dict[int, list] = {}   # display_id -> list[np.ndarray] (tối đa N mẫu gần nhất)
        self.last_seen: dict[int, float] = {}

    def update(self, display_id: int, embedding: np.ndarray):
        samples = self.embeddings.setdefault(display_id, [])
        samples.append(embedding)
        if len(samples) > config.REID_MAX_SAMPLES_PER_ENTITY:
            samples.pop(0)
        self.last_seen[display_id] = time.time()

    def match(self, embedding: np.ndarray):
        """Trả về display_id khớp nhất nếu khoảng cách embedding < ngưỡng, ngược lại None."""
        if embedding is None:
            return None
        best_id, best_dist = None, None
        now = time.time()
        for display_id, samples in self.embeddings.items():
            if now - self.last_seen.get(display_id, 0) > config.REID_GALLERY_TTL_SEC:
                continue  # đã quá lâu không thấy lại -> không so khớp nữa (rời hẳn khu vực)
            dists = np.linalg.norm(np.array(samples) - embedding, axis=1)
            d = float(dists.min())
            if best_dist is None or d < best_dist:
                best_dist, best_id = d, display_id
        if best_id is not None and best_dist <= config.REID_MATCH_THRESHOLD:
            return best_id
        return None

    def forget(self, display_id: int):
        """Gỡ 1 thực thể khỏi bộ nhớ Re-ID (khi bị xoá thủ công hoặc tự động giải phóng)."""
        self.embeddings.pop(display_id, None)
        self.last_seen.pop(display_id, None)


def extract_face_embedding(frame_bgr, box):
    """
    Cắt phần ĐẦU/MẶT phía trên bounding box của 1 người (x1,y1,x2,y2), tìm
    khuôn mặt bên trong, trả về embedding 128 chiều -- hoặc None nếu không
    tìm thấy khuôn mặt rõ ràng (quay lưng, góc nghiêng quá, quá xa camera...).
    """
    if not HAS_FACE_RECOGNITION:
        return None
    x1, y1, x2, y2 = [int(v) for v in box]
    h_frame, w_frame = frame_bgr.shape[:2]
    x1, y1 = max(x1, 0), max(y1, 0)
    x2, y2 = min(x2, w_frame), min(y2, h_frame)
    if x2 <= x1 or y2 <= y1:
        return None

    # Chỉ cắt ~35% phía trên bbox (vùng đầu/mặt) để giảm chi phí xử lý
    head_h = max(int((y2 - y1) * 0.35), 20)
    crop = frame_bgr[y1:min(y1 + head_h, y2), x1:x2]
    if crop.size == 0:
        return None

    rgb = np.ascontiguousarray(crop[:, :, ::-1])  # BGR -> RGB cho face_recognition
    try:
        locations = face_recognition.face_locations(rgb, model="hog")
        if not locations:
            return None
        encodings = face_recognition.face_encodings(rgb, known_face_locations=locations)
    except Exception:
        return None
    if not encodings:
        return None
    return encodings[0]
