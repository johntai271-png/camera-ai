"""
person_detector.py — SKILL 1: Phát hiện + THEO DÕI người (tracking).

Dùng YOLO11 + ByteTrack (có sẵn trong ultralytics): mỗi người trong khung được
gán một track_id ỔN ĐỊNH qua các khung hình. Nhờ đó:
    - biết "vẫn là người đó" dù họ di chuyển/quay lưng
    - gắn được danh tính (Tai / người lạ) vào từng người (core/track_registry.py)
    - đếm giờ ở lì theo TỪNG NGƯỜI, không nhầm giữa 2 người ra vào

LƯU Ý: skill này giữ model YOLO RIÊNG (không dùng model_cache chung với skill
object) — vì tracker gắn callback vào predictor của model, nếu dùng chung thì
lệnh predict() của skill object sẽ làm loạn trạng thái tracker.
"""

from __future__ import annotations
from core.skill_base import Skill, Detection


class PersonDetector(Skill):
    name = "person"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        # cấu hình mặc định, có thể ghi đè trong config.yaml
        self.model_path = self.config.get("model", "yolo11n.pt")  # n=nhẹ nhất, hợp laptop
        self.conf = self.config.get("conf", 0.4)          # ngưỡng tin cậy tối thiểu
        self.device = self.config.get("device", "auto")   # auto = tự chọn GPU/CPU theo máy
        self.alert_when_person = self.config.get("alert_when_person", False)
        self.model = None

    def load(self) -> None:
        from ultralytics import YOLO
        from core.device import yolo_device
        self.device = yolo_device(self.device)   # "auto" -> GPU/MPS/CPU theo máy
        print(f"[person] Đang nạp model {self.model_path} (tracking, device={self.device})...")
        self.model = YOLO(self.model_path)   # model RIÊNG cho tracker (xem chú thích đầu file)
        self._loaded = True
        print("[person] Sẵn sàng.")

    def process(self, frame) -> list[Detection]:
        if not self.enabled or self.model is None:
            return []

        # track() thay vì predict(): giữ ID từng người qua các khung (persist=True)
        results = self.model.track(
            frame, conf=self.conf, classes=[0], device=self.device,
            persist=True, verbose=False,
        )

        detections: list[Detection] = []
        for r in results:
            for b in r.boxes:
                x1, y1, x2, y2 = map(int, b.xyxy[0])
                conf = float(b.conf[0])
                track_id = int(b.id[0]) if b.id is not None else None
                detections.append(Detection(
                    label="Nguoi",
                    confidence=conf,
                    box=(x1, y1, x2, y2),
                    skill=self.name,
                    is_alert=self.alert_when_person,
                    color=(0, 200, 255),               # cam
                    extra={"track_id": track_id},      # danh tính gắn sau (track_registry)
                ))
        return detections
