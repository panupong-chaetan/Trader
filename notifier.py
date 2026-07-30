"""
notifier.py — ยิงแจ้งเตือนเข้า Telegram
========================================
ใช้ร่วมกันได้ทั้ง copilot.py / paper_bot.py / backend
หลักการ: แจ้งเฉพาะ "เหตุการณ์เปลี่ยนสถานะ" ไม่สแปมทุกรอบ loop

ครั้งแรก: แค่ทักหา bot ของคุณใน Telegram สัก 1 ข้อความก่อน
แล้วโค้ดนี้จะค้นหา chat_id ให้เองอัตโนมัติ (เซฟลง telegram_chat.json)
"""

import json
import os
import urllib.request
import urllib.parse

# !! อย่า commit ไฟล์นี้ขึ้น git (ใส่ notifier.py ใน .gitignore หรือย้าย token ไป env)
TOKEN = "8828154865:AAFd-VbzwXZjPDQDOcotyxvNez-ug4-t5sQ"
API = f"https://api.telegram.org/bot{TOKEN}"
CHAT_FILE = "telegram_chat.json"


def _http(url):
    with urllib.request.urlopen(url, timeout=10) as r:
        return json.loads(r.read().decode())


def _find_chat_id():
    """หา chat_id จากข้อความล่าสุดที่คุณทักหา bot"""
    if os.path.exists(CHAT_FILE):
        return json.load(open(CHAT_FILE))["chat_id"]
    data = _http(f"{API}/getUpdates")
    for upd in reversed(data.get("result", [])):
        msg = upd.get("message") or upd.get("edited_message")
        if msg:
            cid = msg["chat"]["id"]
            json.dump({"chat_id": cid}, open(CHAT_FILE, "w"))
            return cid
    return None


def send(text: str) -> bool:
    """ส่งข้อความ คืน True/False — ไม่ throw เพื่อไม่ให้บอทหลักตายเพราะแจ้งเตือนพัง"""
    try:
        cid = _find_chat_id()
        if cid is None:
            print("[notifier] ยังหา chat_id ไม่ได้ — ทัก bot ใน Telegram ก่อน 1 ข้อความ")
            return False
        q = urllib.parse.urlencode({"chat_id": cid, "text": text})
        _http(f"{API}/sendMessage?{q}")
        return True
    except Exception as e:
        print(f"[notifier] ส่งไม่สำเร็จ: {e}")
        return False


# ---------- ตัวช่วยแจ้งเฉพาะตอน "สถานะเปลี่ยน" ----------
_last = {}

def send_on_change(key: str, value, text: str) -> bool:
    """ยิงข้อความเฉพาะเมื่อ value ของ key เปลี่ยนจากครั้งก่อน (กันสแปม)"""
    if _last.get(key) == value:
        return False
    _last[key] = value
    return send(text)


if __name__ == "__main__":
    ok = send("✅ ทดสอบระบบแจ้งเตือน Trading Copilot — ต่อติดแล้ว!")
    print("ส่งสำเร็จ" if ok else "ส่งไม่สำเร็จ — เช็คว่าทัก bot แล้วหรือยัง")
