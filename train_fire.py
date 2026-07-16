"""
train_fire.py — Train model phát hiện lửa/khói tốt hơn trên dataset D-Fire.

Học theo cách các dự án fire-detection tốt hay làm:
    - Bắt đầu từ YOLO11 pretrain (yolo11n.pt) rồi fine-tune (KHÔNG train từ số 0).
    - Dùng D-Fire (~21k ảnh có nhãn fire/smoke) — benchmark phổ biến nhất.
    - imgsz 640, augmentation mặc định của Ultralytics (mosaic, flip, hsv...).
    - Batch nhỏ cho vừa 8GB VRAM của RTX 5070.

CHUẨN BỊ DỮ LIỆU (chọn 1 trong 2):
  A) Tự động qua Kaggle (cần token miễn phí):
       1. kaggle.com -> Settings -> API -> Create New Token -> tải kaggle.json
       2. đặt vào  C:\\Users\\LENOVO\\.kaggle\\kaggle.json
       3. chạy:  python train_fire.py --download
  B) Tải tay: giải nén dataset D-Fire (dạng YOLO) vào thư mục  datasets/dfire/
     sao cho có  datasets/dfire/data.yaml  rồi chạy:  python train_fire.py

Sau khi train xong, model tốt nhất tự copy vào  models/fire.pt  (app dùng ngay).
"""

from __future__ import annotations
import os
import sys
import shutil
import subprocess

DATASET_DIR = os.path.join("datasets", "dfire")
KAGGLE_SLUG = "sayedgamal99/smoke-fire-detection-yolo"  # bản D-Fire đã format YOLO


def download_dfire():
    """Tải D-Fire từ Kaggle (cần kaggle.json)."""
    try:
        import kaggle  # noqa
    except ImportError:
        print("Chưa có thư viện kaggle. Cài:  pip install kaggle")
        sys.exit(1)
    os.makedirs(DATASET_DIR, exist_ok=True)
    print(f"[train] Đang tải {KAGGLE_SLUG} từ Kaggle...")
    subprocess.run(
        ["kaggle", "datasets", "download", "-d", KAGGLE_SLUG,
         "-p", DATASET_DIR, "--unzip"],
        check=True,
    )
    print("[train] Tải xong.")


def find_data_yaml() -> str:
    """Tìm file data.yaml trong thư mục dataset."""
    for root, _, files in os.walk(DATASET_DIR):
        for f in files:
            if f in ("data.yaml", "dfire.yaml", "data.yml"):
                return os.path.join(root, f)
    print(f"Không thấy data.yaml trong {DATASET_DIR}. Kiểm tra lại dữ liệu.")
    sys.exit(1)


def add_feedback_negatives():
    """Trộn ảnh BÁO NHẦM vào tập train làm 'hard negatives'.

    Quy trình sửa báo nhầm (vd vụ nhìn tóc thành khói):
      1. Mỗi lần báo cháy, app tự lưu ảnh GỐC vào data/fire_review/
      2. Bạn xem thư mục đó, ảnh nào là BÁO NHẦM thì chuyển vào data/fire_review/false/
      3. Chạy:  python train_fire.py --with-feedback
    Ảnh trong false/ được thêm vào tập train KHÔNG có nhãn (= "trong ảnh này
    không có lửa/khói") -> model học được là tóc/hoàng hôn/đèn không phải cháy.
    """
    import shutil as sh
    false_dir = os.path.join("data", "fire_review", "false")
    if not os.path.isdir(false_dir):
        print(f"[feedback] Chưa có {false_dir} — bỏ qua.")
        return
    imgs = [f for f in os.listdir(false_dir)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))]
    if not imgs:
        print(f"[feedback] {false_dir} trống — bỏ qua.")
        return
    img_dir = os.path.join(DATASET_DIR, "data", "train", "images")
    lbl_dir = os.path.join(DATASET_DIR, "data", "train", "labels")
    n = 0
    for f in imgs:
        dst_img = os.path.join(img_dir, f"feedback_{f}")
        if os.path.exists(dst_img):
            continue   # đã trộn từ lần trước
        sh.copy(os.path.join(false_dir, f), dst_img)
        # nhãn RỖNG = ảnh nền không có lửa/khói
        stem = os.path.splitext(f"feedback_{f}")[0]
        open(os.path.join(lbl_dir, f"{stem}.txt"), "w").close()
        n += 1
    print(f"[feedback] Đã trộn {n} ảnh báo-nhầm vào tập train làm hard negatives.")


def main():
    if "--download" in sys.argv:
        download_dfire()
    if "--with-feedback" in sys.argv:
        add_feedback_negatives()

    if not os.path.isdir(DATASET_DIR):
        print(f"Chưa có dữ liệu ở {DATASET_DIR}. Xem hướng dẫn ở đầu file.")
        sys.exit(1)

    data_yaml = find_data_yaml()
    print(f"[train] Dùng dataset: {data_yaml}")

    from ultralytics import YOLO
    # chạy --with-feedback: tinh chỉnh tiếp từ model hiện tại (đỡ train lại từ đầu);
    # còn train lần đầu: từ yolo11n pretrain — "đừng làm anh hùng"
    if "--with-feedback" in sys.argv and os.path.exists("models/fire.pt"):
        base = "models/fire.pt"
        epochs = 25
    else:
        base = "yolo11n.pt"
        epochs = 60
    print(f"[train] Fine-tune từ {base}, {epochs} epochs")
    model = YOLO(base)

    # Cài đặt train (theo kinh nghiệm các dự án fire tốt). Chỉnh nếu cần:
    model.train(
        data=data_yaml,
        epochs=epochs,
        imgsz=640,
        batch=8,             # RAM/VRAM máy có hạn: batch 8 (giảm 4 nếu vẫn hết)
        device=0,
        patience=15,         # dừng sớm nếu 15 epoch không cải thiện
        workers=0,           # QUAN TRỌNG (máy RAM ít): 0 = không tạo tiến trình con -> tránh lỗi pagefile
        cache=False,         # không cache ảnh vào RAM
        project="runs_fire",
        name="dfire_yolo11n",
        # augmentation nhẹ giúp bớt báo nhầm hoàng hôn/đèn:
        hsv_h=0.015, hsv_s=0.7, hsv_v=0.4,
        fliplr=0.5, mosaic=1.0,
    )

    # copy model tốt nhất cho app — hỏi trainer đường dẫn THẬT nó đã lưu
    # (ultralytics có thể lồng thư mục theo settings runs_dir, đừng đoán mò)
    best = os.path.join(str(model.trainer.save_dir), "weights", "best.pt")
    if os.path.exists(best):
        os.makedirs("models", exist_ok=True)
        shutil.copy(best, os.path.join("models", "fire.pt"))
        print(f"[train] XONG. Đã cập nhật models/fire.pt từ {best}")
        print("[train] Chạy 'python main.py' để dùng model cháy mới.")
    else:
        print(f"[train] Không thấy {best}. Xem lại log train.")


if __name__ == "__main__":
    main()
