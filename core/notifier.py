"""
notifier.py — Gửi thông báo ra điện thoại.

Hỗ trợ 3 kênh, bật một hoặc NHIỀU cùng lúc (config.yaml -> notify.channels):
    - "ntfy"     : miễn phí, không cần tài khoản. Cài app ntfy, subscribe topic.
    - "telegram" : bot Telegram (tạo bot qua @BotFather lấy token + chat_id).
    - "zalo"     : Zalo Bot API chính thức (https://bot.zapps.me) — tạo bot,
                   lấy token; chat_id là ID cuộc trò chuyện của bạn với bot.
    - "none"     : tắt.

LƯU Ý: chữ trong TIÊU ĐỀ ntfy để KHÔNG DẤU (đi qua HTTP header không chịu
được tiếng Việt có dấu). Nội dung (body) thì thoải mái.

Gửi thông báo mất ~1-3s (gọi mạng) — chấp nhận được vì cảnh báo hiếm và có
cooldown; timeout ngắn để không treo vòng lặp video. Mọi lỗi mạng chỉ in ra,
không bao giờ làm sập app.
"""

from __future__ import annotations
import os
import threading

import requests


class Notifier:
    def __init__(self, config: dict | None = None):
        config = config or {}
        # "channels" (danh sách) ưu tiên hơn "channel" (một kênh, giữ tương thích cũ)
        channels = config.get("channels")
        if not channels:
            channels = [config.get("channel", "none")]
        self.channels = [c for c in channels if c and c != "none"]
        self.ntfy = config.get("ntfy", {})
        self.telegram = config.get("telegram", {})
        self.zalo = config.get("zalo", {})
        self.timeout = config.get("timeout", 5)

    def send(self, title: str, message: str, priority: int = 3,
             tags: list[str] | None = None, image_path: str | None = None) -> None:
        """Gửi 1 thông báo tới TẤT CẢ kênh đang bật.

        Gửi trong THREAD NỀN — tuyệt đối không chặn vòng lặp video (mạng chậm
        5-15s mà chặn là: hình đứng, bộ đếm dwell bị reset, video sự kiện bị cụt).
        Không bao giờ ném lỗi ra ngoài.
        """
        if not self.channels:
            return
        threading.Thread(
            target=self._send_sync,
            args=(title, message, priority, list(tags or []), image_path),
            daemon=True,
        ).start()

    def _send_sync(self, title, message, priority, tags, image_path) -> None:
        # ảnh không tồn tại (imwrite fail...) -> lùi về gửi chữ, đừng mất luôn thông báo
        if image_path and not os.path.exists(image_path):
            image_path = None
        for channel in self.channels:
            try:
                if channel == "ntfy":
                    self._send_ntfy(title, message, priority, tags, image_path)
                elif channel == "telegram":
                    self._send_telegram(title, message, image_path)
                elif channel == "zalo":
                    self._send_zalo(title, message, image_path)
                else:
                    print(f"[notifier] Kênh không hỗ trợ trong config: {channel!r}")
            except Exception as e:
                print(f"[notifier] Gửi thất bại ({channel}): {e}")

    # ---------- ntfy ----------

    def _send_ntfy(self, title, message, priority, tags, image_path):
        server = self.ntfy.get("server", "https://ntfy.sh").rstrip("/")
        topic = self.ntfy.get("topic")
        if not topic:
            print("[notifier] Chưa cấu hình ntfy.topic trong config.yaml.")
            return
        url = f"{server}/{topic}"
        headers = {
            "Title": title,
            "Priority": str(priority),   # 1..5 (5 = khẩn cấp nhất)
            "Tags": ",".join(tags),
        }
        if image_path:
            headers["Filename"] = "alert.jpg"
            headers["Message"] = message
            with open(image_path, "rb") as f:
                requests.put(url, data=f, headers=headers, timeout=self.timeout)
        else:
            requests.put(url, data=message.encode("utf-8"), headers=headers,
                         timeout=self.timeout)

    # ---------- Telegram ----------

    def _send_telegram(self, title, message, image_path):
        token = self.telegram.get("token")
        chat_id = self.telegram.get("chat_id")
        if not token or not chat_id:
            print("[notifier] Chưa cấu hình telegram.token / chat_id.")
            return
        text = f"{title}\n{message}"
        base = f"https://api.telegram.org/bot{token}"
        if image_path:
            with open(image_path, "rb") as f:
                requests.post(f"{base}/sendPhoto",
                              data={"chat_id": chat_id, "caption": text},
                              files={"photo": f}, timeout=self.timeout)
        else:
            requests.post(f"{base}/sendMessage",
                          data={"chat_id": chat_id, "text": text},
                          timeout=self.timeout)

    # ---------- Zalo (Bot API chính thức) ----------
    # Tạo bot: mở app Zalo -> tìm OA "Zalo Bot Manager" -> Create bot -> nhận token.
    # Docs: https://bot.zapps.me/docs/  |  endpoint: bot-api.zaloplatforms.com
    #
    # GỬI ẢNH: sendPhoto của Zalo chỉ nhận URL công khai, không upload được file.
    # Giải pháp: đẩy ảnh lên host tạm (ntfy.sh — link ngẫu nhiên khó đoán, TỰ XOÁ
    # sau ~3 giờ) lấy URL rồi đưa cho Zalo. Không cần cài app ntfy — chỉ mượn
    # làm chỗ chứa. Tắt bằng zalo.send_photo: false (khi đó chỉ gửi chữ).

    def _send_zalo(self, title, message, image_path):
        token = self.zalo.get("token")
        chat_id = self.zalo.get("chat_id")
        if not token or not chat_id:
            print("[notifier] Chưa cấu hình zalo.token / chat_id "
                  "(app Zalo -> OA 'Zalo Bot Manager' -> Create bot).")
            return
        base = self.zalo.get("api_base", "https://bot-api.zaloplatforms.com").rstrip("/")
        text = f"{title}\n{message}"

        # có ảnh -> thử đưa lên host tạm rồi gửi dạng ảnh
        if image_path and self.zalo.get("send_photo", True):
            photo_url = self._host_image_temp(image_path)
            if photo_url:
                try:
                    r = requests.post(f"{base}/bot{token}/sendPhoto",
                                      json={"chat_id": chat_id, "photo": photo_url,
                                            "caption": text},
                                      timeout=self.timeout)
                    if r.status_code == 200 and r.json().get("ok"):
                        return
                    print(f"[notifier] Zalo sendPhoto không nhận ({r.text[:120]}) "
                          f"— lùi về gửi chữ.")
                except Exception as e:
                    print(f"[notifier] Zalo sendPhoto lỗi ({e}) — lùi về gửi chữ.")

        requests.post(f"{base}/bot{token}/sendMessage",
                      json={"chat_id": chat_id, "text": text},
                      timeout=self.timeout)

    def _host_image_temp(self, image_path) -> str | None:
        """Đẩy ảnh lên ntfy.sh làm host tạm, trả về URL công khai (None nếu fail)."""
        server = self.ntfy.get("server", "https://ntfy.sh").rstrip("/")
        topic = self.ntfy.get("topic")
        if not topic:
            return None
        try:
            with open(image_path, "rb") as f:
                r = requests.put(f"{server}/{topic}", data=f,
                                 headers={"Filename": "alert.jpg"},
                                 timeout=self.timeout + 10)
            if r.status_code == 200:
                return (r.json().get("attachment") or {}).get("url")
        except Exception as e:
            print(f"[notifier] Đưa ảnh lên host tạm thất bại: {e}")
        return None
