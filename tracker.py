"""
tracker.py
Bọc (wrap) YOLOv8 + ByteTrack (thư viện ultralytics) để phát hiện & theo dõi
người (person) theo thời gian thực trên Composite Canvas.

Ghi chú hiệu năng: chạy trực tiếp trên GPU local (vd RTX 3060 12GB) để đạt
30-60 FPS cho toàn bộ canvas 3 camera ghép ngang, tránh dùng VLM lớn
(Qwen2-VL, v.v.) cho tác vụ tracking vì độ trễ 1.5-3s/frame là quá cao
cho một hệ thống cảnh báo thời gian thực.
"""

from dataclasses import dataclass
import config
from geometry import compute_foot_point


@dataclass
class Detection:
    track_id: int
    x1: float
    y1: float
    x2: float
    y2: float
    foot_point: tuple
    confidence: float


class PersonTracker:
    def __init__(self, model_path=None, device=None):
        from ultralytics import YOLO  # import trễ để tránh lỗi nếu chưa cài đặt lúc chỉ đọc code
        self.model = YOLO(model_path or config.YOLO_MODEL_PATH)
        self.device = device or config.DEVICE

    def track(self, frame) -> list:
        """
        Chạy YOLOv8 + ByteTrack trên 1 khung hình (Composite Canvas).
        Trả về danh sách Detection với track_id ổn định giữa các frame.
        """
        results = self.model.track(
            source=frame,
            persist=True,
            tracker=config.TRACKER_CONFIG,
            classes=config.YOLO_TARGET_CLASSES,
            conf=config.YOLO_CONFIDENCE_THRESHOLD,
            device=self.device,
            verbose=False,
        )

        detections = []
        if not results:
            return detections

        r = results[0]
        if r.boxes is None or r.boxes.id is None:
            return detections

        boxes_xyxy = r.boxes.xyxy.cpu().numpy()
        track_ids = r.boxes.id.cpu().numpy().astype(int)
        confs = r.boxes.conf.cpu().numpy()

        for (x1, y1, x2, y2), tid, conf in zip(boxes_xyxy, track_ids, confs):
            fx, fy = compute_foot_point(x1, y1, x2, y2)
            detections.append(Detection(
                track_id=int(tid),
                x1=float(x1), y1=float(y1), x2=float(x2), y2=float(y2),
                foot_point=(fx, fy),
                confidence=float(conf),
            ))
        return detections
