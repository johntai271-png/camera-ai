"""
skill_base.py — Nền tảng chung cho mọi "skill" (tính năng) của app.

Mỗi tính năng (phát hiện người, nhận diện mặt, phát hiện cháy) là một class
kế thừa từ `Skill`. Nhờ vậy main.py không cần biết chi tiết bên trong —
nó chỉ gọi .process(frame) và .draw(frame, detections) cho mọi skill giống nhau.
Muốn thêm tính năng mới => tạo 1 file skill mới, không sửa main.py.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Detection:
    """Một kết quả phát hiện trên 1 khung hình."""
    label: str                       # nhãn: "person", "fire", "Nam", "nguoi_la"...
    confidence: float                # độ tin cậy 0.0 - 1.0
    box: tuple[int, int, int, int]   # toạ độ khung: (x1, y1, x2, y2)
    skill: str                       # skill nào tạo ra: "person", "face", "fire"
    is_alert: bool = False           # True nếu cần cảnh báo (vd: cháy, người lạ)
    color: tuple[int, int, int] = (0, 255, 0)   # màu khung vẽ (B, G, R)
    extra: dict = field(default_factory=dict)   # dữ liệu thêm tuỳ skill


class Skill(ABC):
    """
    Lớp cha cho mọi tính năng. Các skill con phải cài đặt `process()`.

    Vòng đời:
        skill = PersonDetector(config)   # tạo
        skill.load()                     # nạp model (chỉ 1 lần khi khởi động)
        dets = skill.process(frame)      # chạy trên từng khung hình
        frame = skill.draw(frame, dets)  # vẽ kết quả lên hình
    """

    name: str = "base"   # tên skill, các con ghi đè

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.enabled: bool = self.config.get("enabled", True)
        self._loaded = False
        # chạy process() mỗi N khung hình (1 = mỗi khung). Skill nặng (mặt) để N>1 cho đỡ lag.
        self.interval: int = max(1, int(self.config.get("interval", 1)))
        # kết quả lần chạy gần nhất — dùng lại (vẽ) cho các khung bị bỏ qua giữa 2 lần chạy
        self._cache: list["Detection"] = []

    # --- các skill con BẮT BUỘC cài đặt 2 hàm dưới ---

    @abstractmethod
    def load(self) -> None:
        """Nạp model / tài nguyên. Gọi 1 lần lúc khởi động."""
        ...

    @abstractmethod
    def process(self, frame) -> list[Detection]:
        """Chạy trên 1 khung hình (numpy BGR), trả về danh sách Detection."""
        ...

    # --- hàm dùng chung, con có thể ghi đè nếu muốn vẽ khác ---

    def draw(self, frame, detections: list[Detection]):
        """Vẽ khung + nhãn lên frame. Trả về frame đã vẽ."""
        import cv2
        for d in detections:
            x1, y1, x2, y2 = d.box
            cv2.rectangle(frame, (x1, y1), (x2, y2), d.color, 2)
            text = f"{d.label} {d.confidence:.0%}"
            cv2.putText(frame, text, (x1, max(y1 - 8, 15)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, d.color, 2)
        return frame

    def __repr__(self):
        return f"<Skill {self.name} enabled={self.enabled}>"
