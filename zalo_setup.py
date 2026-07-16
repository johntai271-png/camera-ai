"""
zalo_setup.py — Lấy chat_id và test kết nối Zalo bot (chạy MỘT lần lúc cài đặt).

TRƯỚC KHI CHẠY, tạo bot (1 phút, làm trên điện thoại):
    1. Mở app Zalo -> ô tìm kiếm gõ "Zalo Bot Manager" -> mở OA đó.
    2. Trong khung chat chọn "Create bot" (Tạo bot). Tên bot phải bắt đầu bằng
       chữ "Bot", ví dụ "Bot Camera Nha".
    3. Tạo xong, Zalo NHẮN cho bạn thông tin bot + BOT TOKEN. Copy token.

RỒI CHẠY:
    python zalo_setup.py <BOT_TOKEN>

Script sẽ:
    - kiểm tra token (getMe)
    - chờ bạn NHẮN 1 TIN bất kỳ cho bot trong app Zalo -> tự lấy chat_id
    - gửi tin nhắn thử "Camera AI ket noi thanh cong!"
    - in ra đúng 2 dòng cần dán vào config.yaml
"""

from __future__ import annotations
import json
import sys
import time

import requests

API_BASE = "https://bot-api.zaloplatforms.com"

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def call(token: str, method: str, **params):
    """Gọi 1 method của Zalo Bot API, trả về dict kết quả."""
    r = requests.post(f"{API_BASE}/bot{token}/{method}",
                      json=params or {}, timeout=30)
    try:
        return r.json()
    except json.JSONDecodeError:
        return {"ok": False, "raw": r.text[:300], "status": r.status_code}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    token = sys.argv[1].strip()

    # 1) kiểm tra token
    me = call(token, "getMe")
    if not me.get("ok"):
        print(f"Token KHÔNG hợp lệ hoặc API đổi. Phản hồi: {me}")
        return
    bot_name = (me.get("result") or {}).get("account_name") \
        or (me.get("result") or {}).get("name") or "bot"
    print(f"✅ Token OK — bot: {bot_name}")

    # 2) chờ tin nhắn để lấy chat_id
    print("\n👉 Bây giờ mở app Zalo, NHẮN 1 TIN bất kỳ cho bot của bạn")
    print("   (tìm tên bot trong Zalo, ví dụ 'Bot Camera Nha', nhắn 'hi').")
    print("   Đang chờ tối đa 120 giây...\n")

    chat_id = None
    deadline = time.time() + 120
    while time.time() < deadline and chat_id is None:
        upd = call(token, "getUpdates", timeout=20)
        if not upd.get("ok"):
            print(f"getUpdates lỗi: {upd}")
            time.sleep(3)
            continue
        results = upd.get("result") or []
        if isinstance(results, dict):        # phòng khi API trả 1 update lẻ
            results = [results]
        for u in results:
            msg = (u or {}).get("message") or {}
            chat = msg.get("chat") or {}
            cid = chat.get("id") or msg.get("chat_id")
            if cid:
                chat_id = str(cid)
                text = msg.get("text", "")
                print(f"✅ Nhận được tin nhắn: {text!r}")
                break
        if chat_id is None:
            time.sleep(2)

    if chat_id is None:
        print("⏰ Hết giờ mà chưa nhận được tin nhắn nào.")
        print("   Kiểm tra: đã nhắn đúng bot chưa? Rồi chạy lại script.")
        return

    # 3) gửi thử
    r = call(token, "sendMessage", chat_id=chat_id,
             text="Camera AI ket noi Zalo thanh cong! 🎉")
    if r.get("ok"):
        print("✅ Đã gửi tin thử — kiểm tra Zalo của bạn!")
    else:
        print(f"⚠️ Gửi thử lỗi: {r}")

    # 4) in phần cần dán vào config
    print("\n===== DÁN VÀO config.yaml (mục notify) =====")
    print(f'  channels: ["ntfy", "zalo"]')
    print(f'  zalo:')
    print(f'    token: "{token}"')
    print(f'    chat_id: "{chat_id}"')
    print(f'    api_base: "{API_BASE}"')


if __name__ == "__main__":
    main()
