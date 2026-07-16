"""
imgio.py — Đọc ảnh an toàn với đường dẫn có dấu tiếng Việt (Windows).

cv2.imread trên Windows dùng API cũ, gặp đường dẫn có ký tự ngoài ASCII
("Thiên Vân", "ảnh mẹ"...) là trả về None âm thầm. Cách chuẩn: đọc bytes
bằng numpy (hiểu Unicode) rồi decode bằng OpenCV.
"""

from __future__ import annotations
import cv2
import numpy as np


def imread_unicode(path: str):
    """Như cv2.imread nhưng chịu được đường dẫn có dấu. Trả None nếu lỗi."""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        if data.size == 0:
            return None
        return cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception:
        return None
