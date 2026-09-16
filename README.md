# pi_bot

Public Pi Telegram Bot repository.

Contains Telegram ↔ Pi Coding Agent integration with UI/UX upgrades.

## Files
- pi_telegram_bot.py
- pi_telegram_mirror_best.py
- pi_telegram_bot_commands.py
- telegram_bot_startup.py
- pi_telegram_bot_vulkan.py (Vulkan-accelerated variant)

## Usage
1. Set your Bot Token:
   ```bash
   export BOT_TOKEN="YOUR_TELEGRAM_BOT_TOKEN"
   ```
2. Set allowed users (your Telegram user ID):
   ```bash
   export ALLOWED_USERS="321127799"
   ```
3. Run the bot:
   ```bash
   python3 pi_telegram_bot.py
   ```

## Security
- **Never hardcode your BOT_TOKEN in the source files**
- The token is read from the `BOT_TOKEN` environment variable
- `ALLOWED_USERS` restricts bot access to specific Telegram user IDs

## Vulkan Acceleration (Optional)
- Install TVM-Vulkan and Mamba-Vulkan runtime for GPU acceleration
- See `mamba-tvm-vulkan/` directory for details
- Vulkan variant: `python3 pi_telegram_bot_vulkan.py`
