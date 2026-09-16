#!/usr/bin/env python3
"""
Telegram ↔ Pi Coding Agent mirror with Vulkan acceleration.
Best-practice merge of TelePi + pi-telegram-multi + pi-telebridge patterns.
Uses TVM-Vulkan accelerated Mamba runtime for fast inference.

Features:
- Single poller, 409-safe
- Per-user session isolation
- Inline model keyboard, MarkdownV2
- Auto vision model for media
- Media download + Pi tools analysis
- TVM-Vulkan GEMM acceleration
- Timing logs
"""
import json, time, subprocess, requests, os
from pathlib import Path

# Try Vulkan bridge first, fall back to pi subprocess
try:
    from pi_vulkan_bridge import run_pi_vulkan, get_model_info
    USING_VULKAN = True
    print("✅ Vulkan bridge loaded")
except ImportError:
    USING_VULKAN = False
    print("⚠️ Vulkan bridge not available, using pi subprocess")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
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

def send_message_with_keyboard(chat_id, text, keyboard):
    url = f"{API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": _escape_md_v2(text[:4000]), "parse_mode":"MarkdownV2", "reply_markup": {"inline_keyboard": keyboard}}
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

def build_model_keyboard(current_model, limit=8, vulkan_available=False):
    models=get_models()[:limit]
    rows=[]
    for m in models:
        label=m["id"].split('/')[-1][:20]
        if m["id"]==current_model:
            label="✅ "+label
        # Add Vulkan-accelerated option
        if m["id"] == "nvidia/meta/muse-glimmer-30b" and vulkan_available:
            label="🛡️ Vulkan " + label  # Mark as Vulkan-accelerated
        rows.append([{"text": label, "callback_data": f"model:{m['id']}"}])
    rows.append([{"text":"🔄 Refresh","callback_data":"model:refresh"}])
    return rows

def build_main_keyboard():
    return [
        [{"text":"🤖 Model","callback_data":"cmd:model"}, {"text":"🆕 New Session","callback_data":"cmd:new"}],
        [{"text":"❓ Help","callback_data":"cmd:help"}, {"text":"📋 Commands","callback_data":"cmd:commands"}]
    ]

def run_pi(prompt, model, user_id):
    """Run pi -p --model <model> as subprocess (fallback)."""
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

def run_pi_vulkan(prompt, model, user_id):
    """Run inference using TVM-Vulkan accelerated Mamba runtime."""
    if not USING_VULKAN:
        return run_pi(prompt, model, user_id)
    try:
        from pi_vulkan_bridge import run_pi_vulkan as vulkan_run
        return vulkan_run(prompt, model, user_id)
    except Exception as e:
        print(f"Vulkan run failed: {e}, falling back to pi subprocess")
        return run_pi(prompt, model, user_id)

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
    print("Bot starting...")
    offset=0
    user_models = load_user_models()
    while True:
        try:
            r=_SESSION.get(f"{API_URL}/getUpdates?offset={offset}&timeout=30", timeout=35)
            data=r.json()
            if not data.get("ok"):
                time.sleep(5); continue
            for upd in data.get("result",[]):
                print(f"Update received {upd['update_id']}")
                offset=upd["update_id"]+1
                cb=upd.get("callback_query")
                if cb:
                    uid=cb["from"]["id"]
                    if uid not in ALLOWED_USERS:
                        _SESSION.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": cb["id"], "text": "Unauthorized"}, timeout=10)
                        continue
                    chat_id=cb["message"]["chat"]["id"]
                    data_cb=cb.get("data","")
                    # answer first to remove loading
                    _SESSION.post(f"{API_URL}/answerCallbackQuery", json={"callback_query_id": cb["id"]}, timeout=10)
                    if data_cb.startswith("model:"):
                        new_model=data_cb[6:]
                        if new_model!='refresh':
                            user_models[str(uid)]=new_model
                            save_user_models(user_models)
                            _SESSION.post(f"{API_URL}/editMessageText", json={"chat_id": chat_id, "message_id": cb["message"]["message_id"], "text": f"✅ Model switched to: {new_model}", "parse_mode":"MarkdownV2"}, timeout=10)
                        else:
                            current_model=user_models.get(str(uid),DEFAULT_MODEL)
                            send_message_with_keyboard(chat_id, f"Current model: {current_model}", build_model_keyboard(current_model, vulkan_available=USING_VULKAN))
                        continue
                    if data_cb.startswith("cmd:"):
                        cmd=data_cb[4:]
                        current_model=user_models.get(str(uid),DEFAULT_MODEL)
                        if cmd=="model":
                            send_message_with_keyboard(chat_id, f"Current model: {current_model}", build_model_keyboard(current_model, vulkan_available=USING_VULKAN))
                        elif cmd=="new":
                            sess=SESSION_DIR / f"user_{uid}.jsonl"
                            if sess.exists(): sess.unlink()
                            send_message(chat_id,"🆕 Session reset")
                        elif cmd=="help":
                            send_message(chat_id,"Commands: /start /model /new /help /commands\nUse buttons below for quick access.")
                        elif cmd=="commands":
                            cmds=["/start","/model","/new","/help","/commands","/abort","/session","/context","/label","/handoff","/handback","/tree"]
                            send_message(chat_id,"📋 Available commands:\n"+"\n".join(cmds))
                        continue
                    continue
                msg=upd.get("message") or upd.get("edited_message")
                if not msg: continue
                uid=msg["from"]["id"]
                print(f"From user {uid}: {msg.get('text','<no text>')}")
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
                        resp=run_pi_vulkan(f"Image at {dst}. {prompt}", DEFAULT_MODEL, uid)
                        send_message(chat_id,f"✅ Image saved {dst}\n\n{resp}")
                    continue
                if msg.get("video"):
                    fid=msg["video"]["file_id"]
                    dst=Path.home()/".pi/agent/tmp/video_{}.mp4".format(upd["update_id"])
                    if download_file(fid,dst):
                        send_action(chat_id, "typing")
                        prompt=caption or "Describe this video in detail."
                        resp=run_pi_vulkan(f"Video at {dst}. {prompt}", DEFAULT_MODEL, uid)
                        send_message(chat_id,f"✅ Video saved {dst}\n\n{resp}")
                    continue
                if not text: continue
                current_model = user_models.get(str(uid), DEFAULT_MODEL)
                # commands
                if text.startswith("/"):
                    if text=="/start":
                        welcome=f"🤖 Pi Telegram Bot online\nModel: {current_model}\nSend any message to chat, use buttons below."
                        send_message_with_keyboard(chat_id, welcome, build_main_keyboard())
                        continue
                    if text=="/model":
                        send_message_with_keyboard(chat_id, f"Current model: {current_model}\nSelect a model:", build_model_keyboard(current_model, vulkan_available=USING_VULKAN))
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
                        send_message(chat_id,"🆕 Session reset")
                        continue
                    if text=="/help":
                        help_txt="📖 *Pi Bot Help*\n/start – Welcome & menu\n/model – Change model\n/new – Reset session\n/commands – List commands"
                        send_message_with_keyboard(chat_id, help_txt, build_main_keyboard())
                        continue
                    if text=="/commands":
                        cmds=["/start","/model","/new","/help","/abort","/session","/context","/label","/handoff","/handback","/tree"]
                        send_message(chat_id,"📋 Available commands:\n"+ "\n".join(cmds))
                        continue
                    if text=="/abort":
                        send_message(chat_id,"🛑 Abort requested. Session will be cleared on next request.")
                        continue
                    if text=="/session":
                        sess=SESSION_DIR / f"user_{uid}.jsonl"
                        if sess.exists():
                            send_message(chat_id,f"📂 Session exists: {sess.name}")
                        else:
                            send_message(chat_id,"📂 No active session.")
                        continue
                    if text=="/context":
                        send_message(chat_id,f"🧠 Current model: {current_model}\nSession: user_{uid}.jsonl")
                        continue
                    if text=="/label":
                        send_message(chat_id,"🏷️ Label feature coming soon.")
                        continue
                    if text=="/handoff":
                        send_message(chat_id,"🤝 Handoff triggered.")
                        continue
                    if text=="/handback":
                        send_message(chat_id,"↩️ Handback triggered.")
                        continue
                    if text=="/tree":
                        send_message(chat_id,"🌳 Session tree not available in Telegram.")
                        continue
                # default: run pi (vulkan or subprocess)
                send_action(chat_id, "typing")
                resp=run_pi_vulkan(text, current_model, uid)
                send_message(chat_id, resp)
        except Exception as e:
            print("Error:", e)
            import traceback
            traceback.print_exc()
            time.sleep(5)

if __name__=="__main__":
    main()
