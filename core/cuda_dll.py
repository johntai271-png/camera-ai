"""
cuda_dll.py — Giúp onnxruntime (InsightFace) chạy GPU chung tiến trình với PyTorch.

BỐI CẢNH:
    Dự án dùng PyTorch (cho YOLO) bản CUDA 12.8, và onnxruntime-gpu (cho InsightFace)
    cũng bản CUDA 12.x. Vì CÙNG phiên bản CUDA, cả hai có thể dùng chung bộ DLL
    cuDNN/CUDA mà PyTorch đã nạp -> không xung đột.

    (Trước đây từng dùng onnxruntime CUDA 13 khác phiên bản với torch CUDA 12 ->
     hai bên tranh nhau cudnn64_9.dll -> nhận diện mặt hỏng. Đã đổi sang cùng CUDA 12.)

CÁCH DÙNG:
    Gọi preload_cuda_dlls() MỘT lần trước khi khởi tạo InsightFace. Nó bảo đảm
    PyTorch đã nạp DLL CUDA, rồi để onnxruntime tái dùng.

Chỉ cần trên Windows; hệ khác là hàm rỗng (không sao).
"""

from __future__ import annotations
import os


def preload_cuda_dlls() -> bool:
    """Bảo đảm DLL CUDA đã sẵn sàng cho onnxruntime. Trả về True nếu chạy được."""
    if os.name != "nt":
        return False
    try:
        import torch  # noqa: F401 — chỉ cần import để nạp DLL CUDA 12.8 của torch
        import onnxruntime as ort
    except ImportError:
        return False

    # ép torch nạp thư viện CUDA vào tiến trình (nếu có GPU)
    try:
        if torch.cuda.is_available():
            torch.zeros(1, device="cuda")
    except Exception:
        pass

    # onnxruntime tự phát hiện torch cùng phiên bản CUDA và tái dùng DLL của torch
    try:
        ort.preload_dlls()
    except Exception:
        pass
    return True
