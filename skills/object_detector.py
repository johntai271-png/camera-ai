"""
object_detector.py — SKILL 4: Phát hiện VẬT đi vào camera (thú, xe...).

Dùng CHUNG model yolo11n.pt với skill person (qua core/model_cache — không tốn
thêm VRAM), chỉ khác danh sách lớp cần bắt. YOLO pretrain sẵn 80 lớp, hay dùng:

    1: xe đạp   2: ô tô     3: xe máy   5: xe buýt   7: xe tải
    14: chim    15: mèo     16: chó

Cấu hình trong config.yaml:
    classes: [15, 16, 2, 3, 1]      # các lớp muốn bắt
    alert_classes: ["cho", "meo"]   # lớp nào xuất hiện thì BÁO điện thoại (rỗng = chỉ vẽ khung)
"""

from __future__ import annotations
from core.skill_base import Skill, Detection
from core.model_cache import get_yolo

# dịch tên lớp COCO (tiếng Anh) -> tiếng Việt không dấu cho de doc
VN_NAMES = {
    "bicycle": "xe_dap", "car": "oto", "motorcycle": "xe_may", "bus": "xe_buyt",
    "truck": "xe_tai", "bird": "chim", "cat": "meo", "dog": "cho",
    "horse": "ngua", "cow": "bo", "sheep": "cuu",
}


class ObjectDetector(Skill):
    name = "object"

    def __init__(self, config: dict | None = None):
        super().__init__(config)
        self.model_path = self.config.get("model", "yolo11n.pt")
        self.conf = self.config.get("conf", 0.45)
        self.device = self.config.get("device", "auto")   # auto = tự chọn theo máy
        self.classes = self.config.get("classes", [15, 16, 2, 3, 1])
        self.alert_classes = set(self.config.get("alert_classes", []))
        self.model = None

    def load(self) -> None:
        from core.device import yolo_device
        self.device = yolo_device(self.device)
        print(f"[object] Dùng chung model {self.model_path} "
              f"(bắt {len(self.classes)} loại vật, device={self.device})...")
        self.model = get_yolo(self.model_path)   # cache: không nạp lần 2
        self._loaded = True
        print("[object] Sẵn sàng.")

    def process(self, frame) -> list[Detection]:
        if not self.enabled or self.model is None:
            return []

        results = self.model.predict(
            frame, conf=self.conf, classes=self.classes,
            device=self.device, verbose=False,
        )

        detections: list[Detection] = []
        for r in results:
            for b in r.boxes:
                x1, y1, x2, y2 = map(int, b.xyxy[0])
                conf = float(b.conf[0])
                en_name = r.names[int(b.cls[0])]
                label = VN_NAMES.get(en_name, en_name)
                detections.append(Detection(
                    label=label,
                    confidence=conf,
                    box=(x1, y1, x2, y2),
                    skill=self.name,
                    is_alert=label in self.alert_classes,
                    color=(255, 160, 60),           # xanh dương nhạt
                    extra={"group": "object"},
                ))
        return detections
