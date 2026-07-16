"""
enroll.py — Quản lý người nhà: thêm (quét cam / từ ảnh có sẵn), xem, xoá.

CÁCH DÙNG:
    python enroll.py Ten                    # quét bằng webcam laptop
    python enroll.py Ten --source URL       # quét bằng camera khác (điện thoại...)
        vd: python enroll.py EmGai --source http://192.168.1.191:8080/video
    python enroll.py Ten --from anh1.jpg anh2.jpg   # nạp từ ảnh có sẵn
    python enroll.py Ten --from thu_muc_anh         # nạp cả thư mục ảnh
    python enroll.py --list                 # xem danh sách người đã đăng ký
    python enroll.py --remove Ten           # xoá một người

Khi quét bằng cam: SPACE = chụp (1 tấm là đủ, thêm vài góc càng tốt), Q = xong.
Ảnh lưu vào data/faces/<Ten>/ — chạy lại main.py để hệ thống học người mới.
"""

from __future__ import annotations
import os
import shutil
import sys

import cv2

FACES_DIR = os.path.join("data", "faces")

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _load_face_app():
    """Nạp InsightFace (tự chọn GPU/CPU) — dùng để kiểm tra ảnh có mặt rõ không."""
    from core.cuda_dll import preload_cuda_dlls
    from core.device import face_ctx_id
    ctx = face_ctx_id("auto")
    if ctx >= 0:
        preload_cuda_dlls()
    from insightface.app import FaceAnalysis
    print("[enroll] Đang nạp bộ nhận diện mặt...")
    app = FaceAnalysis(name="buffalo_l",
                       providers=(["CUDAExecutionProvider", "CPUExecutionProvider"]
                                  if ctx >= 0 else ["CPUExecutionProvider"]))
    app.prepare(ctx_id=ctx, det_size=(640, 640))
    return app


def _next_index(out_dir: str) -> int:
    os.makedirs(out_dir, exist_ok=True)
    return len([f for f in os.listdir(out_dir)
                if f.lower().endswith((".jpg", ".jpeg", ".png"))])


def list_people():
    if not os.path.isdir(FACES_DIR) or not os.listdir(FACES_DIR):
        print("Chưa có ai được đăng ký. Thêm bằng:  python enroll.py Ten")
        return
    print(f"Người đã đăng ký (trong {FACES_DIR}):")
    for name in sorted(os.listdir(FACES_DIR)):
        pdir = os.path.join(FACES_DIR, name)
        if os.path.isdir(pdir):
            n = len([f for f in os.listdir(pdir)
                     if f.lower().endswith((".jpg", ".jpeg", ".png"))])
            print(f"  - {name}: {n} ảnh")


def remove_person(name: str):
    pdir = os.path.join(FACES_DIR, name)
    if not os.path.isdir(pdir):
        print(f"Không có ai tên '{name}'. Xem danh sách:  python enroll.py --list")
        return
    shutil.rmtree(pdir)
    print(f"Đã xoá '{name}'. Chạy lại main.py để hệ thống quên người này.")


def enroll_from_files(name: str, paths: list[str]):
    """Nạp từ ảnh có sẵn — chỉ nhận ảnh có ĐÚNG MỘT mặt rõ (tránh nạp nhầm mặt người khác)."""
    # gom danh sách file ảnh (nhận cả thư mục)
    files: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            files += [os.path.join(p, f) for f in sorted(os.listdir(p))
                      if f.lower().endswith((".jpg", ".jpeg", ".png"))]
        elif os.path.isfile(p):
            files.append(p)
        else:
            print(f"  Bỏ qua (không tồn tại): {p}")
    if not files:
        print("Không có ảnh nào để nạp.")
        return

    app = _load_face_app()
    out_dir = os.path.join(FACES_DIR, name)
    idx = _next_index(out_dir)
    added = 0
    from core.imgio import imread_unicode
    for f in files:
        img = imread_unicode(f)   # chịu được thư mục có dấu tiếng Việt
        if img is None:
            print(f"  BỎ {os.path.basename(f)}: không đọc được ảnh")
            continue
        faces = app.get(img)
        if len(faces) == 0:
            print(f"  BỎ {os.path.basename(f)}: không thấy mặt")
            continue
        if len(faces) > 1:
            print(f"  BỎ {os.path.basename(f)}: có {len(faces)} mặt — dùng ảnh chỉ có MÌNH {name}")
            continue
        idx += 1
        dst = os.path.join(out_dir, f"{idx}.jpg")
        cv2.imwrite(dst, img)
        added += 1
        print(f"  OK {os.path.basename(f)} -> {dst}")
    print(f"\nĐã thêm {added} ảnh cho '{name}'. Chạy lại main.py để học người mới.")


def enroll_from_camera(name: str, source):
    """Quét trực tiếp từ camera (webcam / điện thoại / RTSP)."""
    app = _load_face_app()
    if isinstance(source, str) and source.isdigit():
        source = int(source)
    cap = (cv2.VideoCapture(source, cv2.CAP_FFMPEG)
           if isinstance(source, str) else cv2.VideoCapture(source))
    if not cap.isOpened():
        print(f"[enroll] Không mở được nguồn {source!r}. "
              f"Camera điện thoại: nhớ Start server trong app IP Webcam.")
        return

    out_dir = os.path.join(FACES_DIR, name)
    saved = _next_index(out_dir)
    print(f"[enroll] Đăng ký cho '{name}' từ {source!r}. "
          f"SPACE = chụp, Q = xong. (đã có {saved} ảnh)")

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        faces = app.get(frame)
        view = frame.copy()
        if faces:
            f = max(faces, key=lambda x: (x.bbox[2]-x.bbox[0])*(x.bbox[3]-x.bbox[1]))
            x1, y1, x2, y2 = map(int, f.bbox)
            cv2.rectangle(view, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(view, "SPACE de chup", (x1, max(y1-10, 20)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
        else:
            cv2.putText(view, "Khong thay mat - dua mat vao khung", (20, 40),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(view, f"Da luu: {saved}   |   Q = xong", (20, view.shape[0]-20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
        cv2.imshow(f"Dang ky khuon mat: {name}", view)

        key = cv2.waitKey(1) & 0xFF
        if key == ord("q"):
            break
        if key == ord(" "):
            if not faces:
                print("[enroll] Chưa thấy mặt, chưa lưu.")
                continue
            if len(faces) > 1:
                print(f"[enroll] Có {len(faces)} mặt trong hình — để MÌNH {name} vào khung rồi chụp.")
                continue
            saved += 1
            os.makedirs(out_dir, exist_ok=True)
            path = os.path.join(out_dir, f"{saved}.jpg")
            cv2.imwrite(path, frame)
            print(f"[enroll] Đã lưu {path}")

    cap.release()
    cv2.destroyAllWindows()
    print(f"[enroll] Xong. '{name}' có {saved} ảnh. Chạy lại main.py để học người mới.")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        list_people()
        return
    if args[0] == "--list":
        list_people()
        return
    if args[0] == "--remove":
        if len(args) < 2:
            print("Thiếu tên. Dùng:  python enroll.py --remove Ten")
            return
        remove_person(args[1])
        return

    # tên = mọi chữ trước --from/--source (lỡ gõ tên có khoảng trắng thì tự nối lại)
    flags_at = [args.index(f) for f in ("--from", "--source") if f in args]
    name_end = min(flags_at) if flags_at else len(args)
    name = "".join(a.strip() for a in args[:name_end])
    if not name.isascii():
        print(f"⚠️  Tên '{name}' có dấu tiếng Việt — chữ trên khung hình sẽ bị lỗi font.")
        print(f"    Khuyên dùng tên không dấu, ví dụ: {name.encode('ascii', 'ignore').decode() or 'ThienVan'}")
        print("    (vẫn tiếp tục với tên bạn đặt...)")

    if "--from" in args:
        i = args.index("--from")
        # PowerShell hay dính dấu " vào cuối path khi gõ 'duong\dan\' -> gột sạch
        paths = [p.strip('"').strip("'") for p in args[i + 1:]]
        enroll_from_files(name, paths)
    elif "--source" in args:
        i = args.index("--source")
        if i + 1 >= len(args):
            print("Thiếu URL. Dùng:  python enroll.py Ten --source http://ip:8080/video")
            return
        enroll_from_camera(name, args[i + 1])
    else:
        enroll_from_camera(name, 0)   # mặc định: webcam laptop


if __name__ == "__main__":
    main()
