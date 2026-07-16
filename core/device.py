"""
device.py — Tự chọn phần cứng chạy AI, để ai tải về cũng chạy được.

Config để device: "auto" (mặc định) thì:
    - Có GPU NVIDIA  -> chạy CUDA (nhanh nhất)
    - Máy Mac M1/M2+ -> chạy MPS (GPU của Apple)
    - Còn lại        -> CPU (chậm hơn nhưng vẫn chạy — app sẽ tự cảnh báo
                        và gợi ý chỉnh config cho nhẹ)

Ai muốn ép cứng thì vẫn ghi device: 0 hoặc "cpu" như cũ.
"""

from __future__ import annotations


def yolo_device(value="auto"):
    """Chỗ chạy cho các model YOLO (person/fire/object). Trả về 0 | "mps" | "cpu"."""
    if value != "auto":
        return value
    try:
        import torch
        if torch.cuda.is_available():
            return 0
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"   # GPU máy Mac
    except ImportError:
        pass
    return "cpu"


def face_ctx_id(value="auto") -> int:
    """Chỗ chạy cho InsightFace (nhận mặt). Trả về 0 (GPU) | -1 (CPU)."""
    if value != "auto":
        return int(value)
    try:
        import onnxruntime as ort
        if "CUDAExecutionProvider" in ort.get_available_providers():
            return 0
    except ImportError:
        pass
    return -1


def describe() -> str:
    """Mô tả ngắn phần cứng đã chọn (in lúc khởi động)."""
    dev = yolo_device()
    if dev == 0:
        try:
            import torch
            return f"GPU NVIDIA ({torch.cuda.get_device_name(0)})"
        except Exception:
            return "GPU NVIDIA"
    if dev == "mps":
        return "GPU Apple (MPS)"
    return "CPU (không thấy GPU — chạy được nhưng chậm, xem check_env.py để tối ưu)"
