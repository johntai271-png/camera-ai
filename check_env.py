"""
check_env.py — Khám máy trước khi chạy: thiếu gì, chạy được ở mức nào, cài gì.

Chạy:  python check_env.py
Dành cho người mới tải repo về — nó nói thẳng máy bạn thuộc loại nào và
copy-paste lệnh cài cho đúng.
"""

from __future__ import annotations
import importlib
import platform
import shutil
import subprocess
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

OK, WARN, BAD = "✅", "⚠️ ", "❌"


def has(module: str) -> bool:
    try:
        importlib.import_module(module)
        return True
    except Exception:
        return False


def main():
    print("=" * 60)
    print("KHÁM MÁY CHO CAMERA AI")
    print("=" * 60)

    # --- Hệ điều hành & Python ---
    print(f"\n[Hệ thống] {platform.system()} {platform.release()} | "
          f"Python {sys.version.split()[0]}")
    if sys.version_info < (3, 10):
        print(f"{BAD} Python quá cũ (cần >= 3.10). Cài Python mới hơn trước.")
        return

    # --- GPU NVIDIA? ---
    gpu_name = None
    if shutil.which("nvidia-smi"):
        try:
            out = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=10)
            gpu_name = out.stdout.strip().splitlines()[0] if out.returncode == 0 else None
        except Exception:
            pass
    print(f"[GPU] " + (f"{OK} NVIDIA: {gpu_name}" if gpu_name
                       else f"{WARN}Không thấy GPU NVIDIA — sẽ chạy CPU (chậm hơn)"))

    # --- Thư viện ---
    print("\n[Thư viện]")
    missing_core = [m for m in ("cv2", "yaml", "numpy", "requests")
                    if not has(m.split(".")[0])]
    print((f"{OK} opencv/yaml/numpy/requests đủ" if not missing_core
           else f"{BAD} Thiếu: {missing_core} -> pip install -r requirements.txt"))

    torch_ok = has("torch")
    cuda_ok = False
    if torch_ok:
        import torch
        cuda_ok = torch.cuda.is_available()
        mps_ok = bool(getattr(torch.backends, "mps", None)
                      and torch.backends.mps.is_available())
        tag = "CUDA (GPU NVIDIA)" if cuda_ok else ("MPS (GPU Mac)" if mps_ok else "CPU")
        print(f"{OK} torch {torch.__version__} — chạy {tag}")
        if gpu_name and not cuda_ok:
            print(f"{WARN}Máy CÓ GPU NVIDIA nhưng torch KHÔNG thấy CUDA "
                  f"-> cài nhầm bản CPU. Xem lệnh cài bên dưới.")
    else:
        print(f"{BAD} Chưa có torch. Xem lệnh cài bên dưới.")

    print((f"{OK} ultralytics (YOLO) đủ" if has("ultralytics")
           else f"{BAD} Thiếu ultralytics -> pip install -r requirements.txt"))

    ort_cuda = False
    if has("onnxruntime"):
        import onnxruntime as ort
        ort_cuda = "CUDAExecutionProvider" in ort.get_available_providers()
        print(f"{OK} onnxruntime — nhận diện mặt chạy "
              + ("GPU" if ort_cuda else "CPU (chậm; app tự giảm tải)"))
    else:
        print(f"{WARN}Chưa có onnxruntime -> skill nhận mặt sẽ tự TẮT, phần khác vẫn chạy")

    print((f"{OK} insightface đủ" if has("insightface")
           else f"{WARN}Thiếu insightface -> skill nhận mặt tự TẮT"))

    # --- Model cháy ---
    import os
    print("\n[Model cháy]")
    for p, label in (("models/fire.pt", "fire (đám cháy)"),
                     ("models/fire_small.pt", "fire_small (lửa nhỏ)")):
        print((f"{OK} {label}: có" if os.path.exists(p)
               else f"{WARN}{label}: chưa có -> skill tự tắt "
                    f"(train: python train_fire.py --download, hoặc tắt trong config)"))

    # --- Kết luận + lệnh cài đúng cho máy này ---
    print("\n" + "=" * 60)
    print("LỆNH CÀI CHO MÁY NÀY (copy-paste):")
    print("=" * 60)
    if gpu_name:
        newer = any(x in gpu_name for x in ("RTX 50", "RTX 40", "B", "Ada"))
        idx = "cu128" if newer else "cu126"
        print(f"""
# 1) PyTorch GPU ({idx}):
pip install torch torchvision --index-url https://download.pytorch.org/whl/{idx}

# 2) onnxruntime GPU (PHẢI bản CUDA-12, cùng CUDA với torch):
pip install onnxruntime-gpu --index-url https://aiinfra.pkgs.visualstudio.com/PublicPackages/_packaging/onnxruntime-cuda-12/pypi/simple/

# 3) Phần còn lại:
pip install -r requirements.txt""")
    else:
        print("""
# Máy không có GPU NVIDIA — cài bản CPU (chạy được, chậm hơn):
# 1) PyTorch CPU:
pip install torch torchvision

# 2) onnxruntime CPU:
pip install onnxruntime

# 3) Phần còn lại:
pip install -r requirements.txt

# Mẹo cho máy CPU (config.yaml): tăng interval các skill lên gấp đôi,
# giảm video width/height xuống 640x480 — app sẽ chạy mượt hơn nhiều.""")

    print("\nXong. Chạy thử:  python main.py")


if __name__ == "__main__":
    main()
