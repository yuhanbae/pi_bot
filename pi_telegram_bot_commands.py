#!/usr/bin/env python3
"""Pi Telegram Bot with Pi command mapping
Send /pi <command> to execute pi commands directly
"""
import os
import time
import subprocess
import requests
import json

BOT_TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"
ALLOWED_USER_ID = 321127799
API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}"
DEFAULT_MODEL = "nvidia/meta/muse-glimmer-30b"

def send_message(chat_id, text):
    if len(text) > 4000:
        text = text[:3900] + "\n... [Output truncated]"
    url = f"{API_URL}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    try:
        r = requests.post(url, json=payload, timeout=30)
        if not r.json().get("ok"):
            payload.pop("parse_mode", None)
            requests.post(url, json=payload, timeout=30)
    except Exception as e:
        print(f"Error sending message: {e}")

def run_pi_command(args_list):
    try:
        cmd = ["pi"] + args_list
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd="/data/data/com.termux/files/home")
        output = result.stdout.strip()
        if result.stderr.strip():
            output += f"\n[stderr:\n{result.stderr.strip()}]"
        return output or "Command executed with no output"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 120 seconds"
    except Exception as e:
        return f"Error: {str(e)}"

def run_pi_prompt(prompt, model=None):
    try:
        cmd = ["pi", "-p"]
        if model:
            cmd.extend(["--model", model])
        cmd.append(prompt)
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120, cwd="/data/data/com.termux/files/home")
        output = result.stdout.strip()
        if result.stderr.strip():
            output += f"\n[stderr:\n{result.stderr.strip()}]"
        return output or "Command executed with no output"
    except subprocess.TimeoutExpired:
        return "Error: Pi execution timed out after 120 seconds"
    except Exception as e:
        return f"Error: {str(e)}"

def main():
    print("Starting Pi Telegram Bot with command mapping...")
    global DEFAULT_MODEL
    offset = 0
    
    while True:
        try:
            url = f"{API_URL}/getUpdates?offset={offset}&timeout=30"
            r = requests.get(url, timeout=35)
            data = r.json()
            if not data.get("ok"):
                time.sleep(5)
                continue
                
            for update in data.get("result", []):
                offset = update["update_id"] + 1
                message = update.get("message") or update.get("edited_message")
                if not message:
                    continue
                    
                user_id = message.get("from", {}).get("id")
                chat_id = message.get("chat", {}).get("id")
                text = message.get("text", "").strip()
                
                if user_id != ALLOWED_USER_ID:
                    send_message(chat_id, "Unauthorized.")
                    continue
                if not text:
                    continue
                
                print(f"Received: {text}")
                
                # Command routing
                if text == "/start":
                    help_text = """🤖 *Pi Telegram Bot - Pi Commands Enabled*

*Commands:*
/start - Show this help
/model - Show current model
/model <name> - Switch model
/pi <args> - Execute pi command directly
/ls - List files
/ls path - List directory
/cat file - Read file
/echo text - Test command

*Examples:*
/pi list-models
/pi --models agnes/*
/pi config

*Usage:*
Send any prompt for AI chat, or use /pi for direct commands.
"""
                    send_message(chat_id, help_text)
                    continue
                
                if text == "/model":
                    send_message(chat_id, f"Current model: {DEFAULT_MODEL}\nUsage: /model <model-name>")
                    continue
                
                if text.startswith("/model "):
                    DEFAULT_MODEL = text[7:].strip()
                    send_message(chat_id, f"✅ Model switched to: {DEFAULT_MODEL}")
                    continue
                
                if text.startswith("/pi "):
                    requests.post(f"{API_URL}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})
                    args = text[4:].strip().split()
                    output = run_pi_command(args)
                    send_message(chat_id, f"```\n{output}\n```")
                    continue
                
                # Quick shortcuts for common pi operations
                if text.startswith("/ls "):
                    path = text[4:].strip() or "."
                    result = subprocess.run(["ls", "-la", path], capture_output=True, text=True)
                    send_message(chat_id, f"```\n{result.stdout}\n```")
                    continue
                
                if text.startswith("/ls"):
                    result = subprocess.run(["ls", "-la"], capture_output=True, text=True)
                    send_message(chat_id, f"```\n{result.stdout}\n```")
                    continue
                
                if text.startswith("/cat "):
                    filepath = text[5:].strip()
                    try:
                        with open(filepath, 'r') as f:
                            content = f.read()
                        send_message(chat_id, f"```\n{content[:4000]}\n```")
                    except Exception as e:
                        send_message(chat_id, f"Error reading file: {e}")
                    continue
                
                # Default: treat as AI prompt
                requests.post(f"{API_URL}/sendChatAction", json={"chat_id": chat_id, "action": "typing"})
                response = run_pi_prompt(text, DEFAULT_MODEL)
                send_message(chat_id, response)
                
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
