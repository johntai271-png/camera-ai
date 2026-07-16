"""
model_cache.py — Cache model YOLO dùng chung giữa các skill.

Skill 'person' và 'object' cùng dùng file yolo11n.pt. Nếu mỗi skill tự nạp
một bản riêng thì tốn VRAM gấp đôi và chậm khởi động. File này giữ MỘT bản
cho mỗi đường dẫn model, ai cần thì lấy ra dùng chung.
"""

from __future__ import annotations

_cache: dict[str, object] = {}


def get_yolo(model_path: str):
    """Trả về model YOLO cho đường dẫn này (nạp 1 lần duy nhất)."""
    if model_path not in _cache:
        from ultralytics import YOLO
        _cache[model_path] = YOLO(model_path)
    return _cache[model_path]
