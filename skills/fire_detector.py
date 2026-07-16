"""
fire_detector.py — SKILL 3: Phát hiện cháy / khói.

Dùng một model YOLO được train riêng cho lửa & khói (khác với YOLO người ở trên,
vì model 80-class mặc định KHÔNG có class "fire").

QUAN TRỌNG — cần 1 file model cháy:
    Đặt file .pt vào  models/fire.pt  rồi khai trong config.yaml.
    Nguồn model có sẵn (không cần tự train):
      - Tìm trên Hugging Face / GitHub: "YOLO fire smoke detection .pt"
      - Hoặc tự train từ dataset D-Fire (~21k ảnh có nhãn) — xem README mục "Train cháy".
    NẾU CHƯA CÓ model: skill này tự động tắt, app vẫn chạy bình thường (người + mặt).

Vì báo cháy nhầm rất phiền, mặc định chỉ cảnh báo khi thấy lửa/khói liên tục
nhiều khung hình (min_streak) chứ không phải chớp 1 cái là hú còi.
"""

from __future__ import annotations
import os
from collections import deque
from core.skill_base import Skill, Detection


class FireDetector(Skill):
    name = "fire"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.model_path = self.config.get("model", "models/fire.pt")
        self.conf = self.config.get("conf", 0.5)
        self.device = self.config.get("device", "auto")   # auto = tự chọn theo máy
        self.min_streak = self.config.get("min_streak", 3)   # số khung liên tiếp để chắc ăn
        # chỉ các nhãn này mới được BÁO ĐỘNG (vẫn vẽ khung mọi nhãn).
        # vd model lửa-nhỏ hay nhìn tóc đen thành "smoke" -> để ["fire"] cho đỡ báo nhầm
        self.alert_labels = {s.lower() for s in self.config.get("alert_labels", ["fire", "smoke"])}
        self.model = None
        self._recent = deque(maxlen=self.min_streak)  # lịch sử "có thấy lửa" gần đây

    def load(self) -> None:
        if not os.path.exists(self.model_path):
            print(f"[fire] KHÔNG thấy model {self.model_path} => TẮT skill cháy. "
                  f"(app vẫn chạy người + mặt bình thường)")
            self.enabled = False
            return
        from core.model_cache import get_yolo
        from core.device import yolo_device
        self.device = yolo_device(self.device)
        print(f"[fire] Đang nạp model cháy {self.model_path} (device={self.device})...")
        self.model = get_yolo(self.model_path)   # nhiều camera dùng chung 1 bản
        self._loaded = True
        print("[fire] Sẵn sàng.")

    def process(self, frame) -> list[Detection]:
        if not self.enabled or self.model is None:
            return []

        results = self.model.predict(
            frame, conf=self.conf, device=self.device, verbose=False
        )

        detections: list[Detection] = []
        saw_fire = False
        for r in results:
            names = r.names  # bản đồ id -> tên class của model cháy
            for b in r.boxes:
                x1, y1, x2, y2 = map(int, b.xyxy[0])
                conf = float(b.conf[0])
                cls = names[int(b.cls[0])].lower()
                if cls in self.alert_labels:
                    saw_fire = True   # chỉ nhãn được phép báo mới nuôi chuỗi xác nhận
                detections.append(Detection(
                    label=cls.upper(),                 # "FIRE" / "SMOKE"
                    confidence=conf,
                    box=(x1, y1, x2, y2),
                    skill=self.name,
                    is_alert=False,   # tạm thời False, quyết định thật ở dưới
                    color=(0, 0, 255),
                    # mọi instance (fire, fire_small...) đều báo chung nhóm "fire"
                    extra={"group": "fire"},
                ))

        # Chống báo nhầm: chỉ bật cảnh báo khi thấy lửa nhiều khung liên tiếp,
        # và chỉ cho các nhãn nằm trong alert_labels
        self._recent.append(saw_fire)
        confirmed = len(self._recent) == self.min_streak and all(self._recent)
        if confirmed:
            for d in detections:
                if d.label.lower() in self.alert_labels:
                    d.is_alert = True

        return detections
