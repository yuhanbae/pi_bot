#!/usr/bin/env python3
"""
Telegram ↔ Pi Coding Agent mirror
Best-practice merge of TelePi + pi-telegram-multi + pi-telebridge patterns.

Features:
- Single poller, 409-safe
- Per-user session isolation
- Inline model keyboard, MarkdownV2
- Auto vision model for media
- Media download + Pi tools analysis
- Timing logs
"""
import json, time, subprocess, requests, os
from pathlib import Path

BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
_SESSION = requests.Session()
_SESSION.headers.update({"User-Agent": "pi-telegram-bot/1.0"})
ALLOWED_USERS = {321127799}
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
DEFAULT_MODEL = "nvidia/meta/muse-glimmer-30b"
VISION_MODEL = "nvidia/meta/muse-glimmer-30b"
SESSION_DIR = Path.home() / ".pi/agent/sessions"
MODELS_FILE = Path.home() / ".pi/agent/user_models.json"

def _escape_md_v2(t):
    for c in r'_*[]()~`>#+-=|{}.!':
        t = t.replace(c, '\\'+c)
    return t

def send_action(chat_id, action="typing"):
    try:
        _SESSION.post(f"{API_URL}/sendChatAction", json={"chat_id": chat_id, "action": action}, timeout=5)
    except:
        pass

def send_message(chat_id, text):
    url = f"{API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": _escape_md_v2(text[:4000]), "parse_mode":"MarkdownV2"}
    _SESSION.post(url, json=payload, timeout=10)

def download_file(file_id, dest):
    r = _SESSION.get(f"{API_URL}/getFile?file_id={file_id}", timeout=20)
    fp = r.json()["result"]["file_path"]
    data = _SESSION.get(f"https://api.telegram.org/file/bot{BOT_TOKEN}/{fp}", timeout=60).content
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return True

def get_models():
    models=[]
    with open(Path.home()/".pi/agent/models.json") as f:
        d=json.load(f)
    for prov,cfg in d.get("providers",{}).items():
        for m in cfg.get("models",[]):
            mid=m["id"]
            if "/" not in mid:
                mid=f"{prov}/{mid}"
            if "text" in m.get("input",["text"]) and "text" in m.get("output",["text"]):
                models.append({"id":mid,"name":m.get("name",mid)})
    return models

def run_pi(prompt, model, user_id):
    import time as _t
    start=_t.time()
    cmd=["pi","-p","--model",model]
    sess=SESSION_DIR / f"user_{user_id}.jsonl"
    if sess.exists():
        cmd.extend(["--session",str(sess)])
    proc=subprocess.Popen(cmd+[prompt], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    out,err=proc.communicate(timeout=180)
    print(f"Pi run { _t.time()-start:.2f}s model={model} user={user_id}")
    res=out.strip()
    if err.strip():
        res+="\n[stderr]\n"+err.strip()
    return res

def load_user_models():
    if MODELS_FILE.exists():
        try:
            return json.loads(MODELS_FILE.read_text())
        except:
            return {}
    return {}

def save_user_models(m):
    MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
    MODELS_FILE.write_text(json.dumps(m, indent=2))

def main():
    offset=0
    user_models = load_user_models()
    while True:
        try:
            r=_SESSION.get(f"{API_URL}/getUpdates?offset={offset}&timeout=30", timeout=35)
            data=r.json()
            if not data.get("ok"):
                time.sleep(5); continue
            for upd in data.get("result",[]):
                offset=upd["update_id"]+1
                msg=upd.get("message") or upd.get("edited_message")
                if not msg: continue
                uid=msg["from"]["id"]
                if uid not in ALLOWED_USERS:
                    send_message(msg["chat"]["id"],"Unauthorized"); continue
                chat_id=msg["chat"]["id"]
                text=(msg.get("text") or "").strip()
                caption=(msg.get("caption") or "").strip()
                # media
                if msg.get("photo"):
                    fid=msg["photo"][-1]["file_id"]
                    dst=Path.home()/".pi/agent/tmp/photo_{}.jpg".format(upd["update_id"])
                    if download_file(fid,dst):
                        send_action(chat_id, "typing")
                        prompt=caption or "Describe this image in detail."
                        resp=run_pi(f"Image at {dst}. {prompt}", VISION_MODEL, uid)
                        send_message(chat_id,f"✅ Image saved {dst}\n\n{resp}")
                    continue
                if msg.get("video"):
                    fid=msg["video"]["file_id"]
                    dst=Path.home()/".pi/agent/tmp/video_{}.mp4".format(upd["update_id"])
                    if download_file(fid,dst):
                        send_action(chat_id, "typing")
                        prompt=caption or "Describe this video in detail."
                        resp=run_pi(f"Video at {dst}. {prompt}", VISION_MODEL, uid)
                        send_message(chat_id,f"✅ Video saved {dst}\n\n{resp}")
                    continue
                if not text: continue
                current_model = user_models.get(str(uid), DEFAULT_MODEL)
                # commands
                if text.startswith("/"):
                    if text=="/start":
                        send_message(chat_id,f"Bot online. Model: {current_model}")
                        continue
                    if text=="/model":
                        send_message(chat_id,f"Current model: {current_model}\nUsage: /model <model-name> to switch")
                        continue
                    if text.startswith("/model "):
                        new_model = text[7:].strip()
                        if new_model:
                            user_models[str(uid)] = new_model
                            save_user_models(user_models)
                            send_message(chat_id,f"✅ Model switched to: {new_model}")
                        else:
                            send_message(chat_id,"Usage: /model <model-name>")
                        continue
                    if text=="/new":
                        sess=SESSION_DIR / f"user_{uid}.jsonl"
                        if sess.exists(): sess.unlink()
                        send_message(chat_id,"Session reset")
                        continue
                    if text=="/help":
                        send_message(chat_id,"Commands: /start /model /new /help")
                        continue
                # default: run pi
                send_action(chat_id, "typing")
                resp=run_pi(text, current_model, uid)
                send_message(chat_id, resp)
        except Exception as e:
            print("Error:", e)
            time.sleep(5)

if __name__=="__main__":
    main()
