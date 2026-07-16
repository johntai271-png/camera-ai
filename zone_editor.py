"""
zone_editor.py — Vẽ vùng giám sát bằng chuột, trên hình từ BẤT KỲ camera nào.

Chạy:
    python zone_editor.py                             # webcam laptop, lưu data/zones.json
    python zone_editor.py --source http://IP:8080/video --out data/zones_dienthoai.json
                                                      # camera điện thoại/RTSP, lưu file riêng
    python zone_editor.py --image anh.jpg             # vẽ trên 1 tấm ảnh chụp sẵn

Thao tác:
    Chuột trái  = thêm đỉnh cho vùng đang vẽ
    U           = xoá đỉnh vừa thêm
    N           = chốt vùng đang vẽ (tự đặt tên vung-1, vung-2, ...)
    D           = xoá vùng đã chốt gần nhất
    S           = LƯU
    Q           = thoát (nhớ nhấn S trước nếu muốn giữ)

Muốn đổi tên vùng ("vung-1" -> "cong"): mở file json sửa chữ là xong.
Vẽ xong phải CHẠY LẠI app để vùng mới có hiệu lực.
"""

from __future__ import annotations
import json
import os
import sys

import cv2
import numpy as np

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _arg(flag: str, default: str | None = None) -> str | None:
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


ZONES_FILE = _arg("--out", os.path.join("data", "zones.json"))


def load_zones() -> list[dict]:
    if os.path.exists(ZONES_FILE):
        try:
            with open(ZONES_FILE, "r", encoding="utf-8") as f:
                return json.load(f).get("zones", [])
        except json.JSONDecodeError:
            pass
    return []


def save_zones(zones: list[dict]) -> None:
    os.makedirs(os.path.dirname(ZONES_FILE) or ".", exist_ok=True)
    with open(ZONES_FILE, "w", encoding="utf-8") as f:
        json.dump({"zones": zones}, f, ensure_ascii=False, indent=2)
    print(f"[editor] Đã lưu {len(zones)} vùng vào {ZONES_FILE}")


def main():
    # nguồn hình: ảnh tĩnh / webcam / camera IP (URL)
    image = None
    img_path = _arg("--image")
    if img_path:
        image = cv2.imread(img_path)
        if image is None:
            print(f"Không đọc được ảnh: {img_path}")
            return
    cap = None
    if image is None:
        src = _arg("--source", "0")
        if src.isdigit():
            cap = cv2.VideoCapture(int(src))
        else:
            cap = cv2.VideoCapture(src, cv2.CAP_FFMPEG)   # http/rtsp
        if not cap.isOpened():
            print(f"Không mở được nguồn {src!r}. Camera điện thoại: nhớ Start server; "
                  f"webcam: đóng app đang chiếm cam; hoặc dùng --image.")
            return

    zones = load_zones()
    current: list[list[float]] = []   # các đỉnh (chuẩn hoá) của vùng đang vẽ
    size = {"w": 1, "h": 1}

    def on_mouse(event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN:
            current.append([x / size["w"], y / size["h"]])

    win = "Ve vung giam sat  |  Trai=diem  N=chot  U=lui  D=xoa vung  S=luu  Q=thoat"
    cv2.namedWindow(win)
    cv2.setMouseCallback(win, on_mouse)
    print(__doc__)

    while True:
        if image is not None:
            frame = image.copy()
        else:
            ok, frame = cap.read()
            if not ok:
                break
        h, w = frame.shape[:2]
        size["w"], size["h"] = w, h

        # vẽ các vùng đã chốt
        for z in zones:
            pts = np.array([[int(px * w), int(py * h)] for px, py in z["points"]],
                           dtype=np.int32)
            cv2.polylines(frame, [pts], True, (255, 200, 0), 2)
            cv2.putText(frame, z["name"], (pts[0][0] + 4, pts[0][1] - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 200, 0), 2)
        # vẽ vùng đang thao tác (xanh lá)
        if current:
            pts = np.array([[int(px * w), int(py * h)] for px, py in current],
                           dtype=np.int32)
            cv2.polylines(frame, [pts], False, (0, 255, 0), 2)
            for p in pts:
                cv2.circle(frame, tuple(p), 4, (0, 255, 0), -1)

        cv2.putText(frame, f"Vung da luu: {len(zones)} | dinh dang ve: {len(current)}",
                    (10, h - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
        cv2.imshow(win, frame)

        key = cv2.waitKey(30) & 0xFF
        if key == ord("q"):
            break
        elif key == ord("u") and current:
            current.pop()
        elif key == ord("n"):
            if len(current) >= 3:
                zones.append({"name": f"vung-{len(zones) + 1}", "points": current[:]})
                print(f"[editor] Đã chốt 'vung-{len(zones)}' ({len(current)} đỉnh). "
                      f"Đổi tên trong {ZONES_FILE} nếu muốn.")
                current.clear()
            else:
                print("[editor] Cần ít nhất 3 đỉnh mới chốt được vùng.")
        elif key == ord("d") and zones:
            gone = zones.pop()
            print(f"[editor] Đã xoá vùng '{gone['name']}'.")
        elif key == ord("s"):
            save_zones(zones)

    if cap is not None:
        cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
