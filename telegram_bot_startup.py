#!/usr/bin/env python3
"""
Telegram Bot Startup Script
Runs the Pi Telegram Bot when pi starts
"""
import subprocess
import sys
import os
import time
from pathlib import Path

def start_telegram_bot():
    """Start the Telegram bot in the background"""
    bot_script = Path.home() / ".pi/agent/pi_telegram_bot.py"
    bot_commands = Path.home() / ".pi/agent/pi_telegram_bot_commands.py"
    
    # Check which bot script exists and is ready
    if bot_script.exists():
        bot_path = str(bot_script)
        bot_name = "pi_telegram_bot (full version)"
    elif bot_commands.exists():
        bot_path = str(bot_commands)
        bot_name = "pi_telegram_bot_commands (command mapping)"
    else:
        print("❌ No Telegram bot script found")
        return False
    
    # Start the bot in background
    try:
        proc = subprocess.Popen(
            [sys.executable, bot_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=Path.home() / ".pi/agent"
        )
        
        # Wait a moment for startup
        time.sleep(2)
        
        # Check if process is still running
        if proc.poll() is None:
            print(f"✅ Telegram bot started: {bot_name}")
            print(f"   PID: {proc.pid}")
            print(f"   Script: {bot_path}")
            return True
        else:
            stderr = proc.stderr.read()
            print(f"❌ Telegram bot failed to start")
            print(f"   Error: {stderr[:200]}")
            return False
    except Exception as e:
        print(f"❌ Error starting Telegram bot: {e}")
        return False

if __name__ == "__main__":
    start_telegram_bot()