import os
import sys
import json
import time
import shutil
import logging
import asyncio
import datetime
import subprocess
import psutil
import re
from typing import Dict, Any, Optional

# Configuration & Constants
BOT_TOKEN = "8597558720:AAE6uGCCT-CSbqHbU5V-DCeIiyoqFpm0iA0" 
ADMIN_ID = 8472327599
OWNER_USERNAME = "@Rolax112"
OFFICIAL_CHANNEL_URL = "https://t.me/rolaxexploitsz"
FORCE_JOIN_CHANNEL = "-1003683777828"
VERSION = "3.18"

# File System Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(BASE_DIR, "users.json")
BOTS_FILE = os.path.join(BASE_DIR, "bots.json")
PENDING_FILE = os.path.join(BASE_DIR, "pending.json")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")
ADMINS_FILE = os.path.join(BASE_DIR, "admins.json")
FORCE_JOIN_FILE = os.path.join(BASE_DIR, "force_join.json")
REDEEM_FILE = os.path.join(BASE_DIR, "redeem_codes.json")
AUDIT_LOG_FILE = os.path.join(BASE_DIR, "audit_logs.txt")
SESSION_LOG_FILE = os.path.join(BASE_DIR, "session_logs.txt")
BUTTON_CLICK_LOG_FILE = os.path.join(BASE_DIR, "button_clicks.txt")
HOSTED_DIR = os.path.join(BASE_DIR, "hosted_bots")
LOGS_DIR = os.path.join(BASE_DIR, "bot_logs")

os.makedirs(HOSTED_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)

RUNNING_PROCESSES: Dict[str, Dict[str, Any]] = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

# ==================== DATABASE HELPERS ====================

def load_json(filename: str, default: Any) -> Any:
    if not os.path.exists(filename):
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4)
        return default
    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Error loading {filename}: {e}")
        return default

def save_json(filename: str, data: Any) -> None:
    try:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving {filename}: {e}")

def get_users() -> dict: return load_json(USERS_FILE, {})
def save_users(data: dict) -> None: save_json(USERS_FILE, data)
def get_bots() -> dict: return load_json(BOTS_FILE, {})
def save_bots(data: dict) -> None: save_json(BOTS_FILE, data)
def get_pending() -> dict: return load_json(PENDING_FILE, {})
def save_pending(data: dict) -> None: save_json(PENDING_FILE, data)
def get_redeem_codes() -> dict: return load_json(REDEEM_FILE, {})
def save_redeem_codes(data: dict) -> None: save_json(REDEEM_FILE, data)

def get_admins() -> list:
    admins = load_json(ADMINS_FILE, [ADMIN_ID])
    if ADMIN_ID not in admins:
        admins.append(ADMIN_ID)
    return [int(a) for a in admins]

def save_admins(admins: list) -> list:
    if ADMIN_ID not in admins:
        admins.append(ADMIN_ID)
    cleaned_admins = list(set([int(a) for a in admins]))
    save_json(ADMINS_FILE, cleaned_admins)
    return cleaned_admins

def is_admin(user_id: int) -> bool:
    if int(user_id) == int(ADMIN_ID):
        return True
    return int(user_id) in get_admins()

def get_force_join() -> list:
    return load_json(FORCE_JOIN_FILE, []) 

def save_force_join(channels: list) -> None:
    save_json(FORCE_JOIN_FILE, channels)

def get_config() -> dict:
    default_cfg = {
        "bot_status": "ON",
        "default_cpu_limit": 8.0,
        "default_ram_limit": 8192,
        "maintenance_mode": False,
        "referral_reward": 0.25,
        "daily_reminder_active": True
    }
    return load_json(CONFIG_FILE, default_cfg)

def save_config(data: dict) -> None: save_json(CONFIG_FILE, data)

def log_audit_action(action: str, admin_id: int = ADMIN_ID) -> None:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] ADMIN (ID: {admin_id}) ACTION: {action}\n"
    with open(AUDIT_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)

def log_session_action(user_id: int, username: str, action: str) -> None:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] User: @{username} (ID: {user_id}) -> {action}\n"
    with open(SESSION_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)

def log_button_click(user_id: int, username: str, button_data: str) -> None:
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] User @{username} (ID: {user_id}) clicked button: {button_data}\n"
    with open(BUTTON_CLICK_LOG_FILE, "a", encoding="utf-8") as f:
        f.write(entry)

async def check_force_join(user_id: int, bot) -> bool:
    if is_admin(user_id):
        return True
    channels = get_force_join()
    if not channels:
        return True  
        
    for ch in channels:
        try:
            chat_id = int(ch) if ch.startswith("-") or ch.isdigit() else ch
            member = await bot.get_chat_member(chat_id=chat_id, user_id=user_id)
            if member.status in ['left', 'kicked', 'restricted']:
                return False
        except Exception as e:
            logger.warning(f"Force join check error for channel {ch}: {e}")
            return True
    return True

# ==================== BACKGROUND GUARDIANS ====================

async def background_expiry_guardian(app: Application):
    while True:
        try:
            now = time.time()
            users = get_users()
            updated = False

            for uid, uinfo in users.items():
                if uinfo.get("premium", False) and uinfo.get("premium_expiry"):
                    if now >= uinfo["premium_expiry"]:
                        uinfo["premium"] = False
                        uinfo["premium_expiry"] = None
                        updated = True
                        try:
                            await app.bot.send_message(
                                chat_id=int(uid),
                                text="Your Premium VIP membership has expired! You are now on the Free tier.",
                                parse_mode="Markdown"
                            )
                        except Exception:
                            pass
            if updated:
                save_users(users)
            await asyncio.sleep(30)
        except Exception as e:
            logger.error(f"Error in Expiry Guardian: {e}")
            await asyncio.sleep(30)

async def daily_reminder_guardian(app: Application):
    while True:
        try:
            await asyncio.sleep(86400)
            config = get_config()
            if config.get("daily_reminder_active", True):
                users = get_users()
                for uid in users:
                    try:
                        await app.bot.send_message(
                            chat_id=int(uid),
                            text="Daily Reminder: Your Python and Node.js bots are running 24/7 on Exclusive Rolax Hosting. Send /start to deploy a new bot!",
                            parse_mode="Markdown"
                        )
                    except Exception:
                        pass
        except Exception as e:
            logger.error(f"Error in Daily Reminder Guardian: {e}")

# ==================== PROCESS ENGINE ====================

def start_bot_process(bot_id: str) -> bool:
    bots = get_bots()
    if bot_id not in bots:
        return False

    binfo = bots[bot_id]
    
    users = get_users()
    owner_id = str(binfo.get("owner_id"))
    if owner_id in users and users[owner_id].get("restricted", False):
        binfo["status"] = "STOPPED"
        save_bots(bots)
        return False

    path = binfo["path"]
    if not os.path.exists(path):
        return False

    stop_bot_process(bot_id)

    log_path = os.path.join(LOGS_DIR, f"bot_{bot_id}.log")
    log_file = open(log_path, "a", encoding="utf-8")

    try:
        bot_dir = os.path.dirname(path)
        runtime = binfo.get("runtime", "python")
        cmd = [sys.executable, path] if runtime == "python" else ["node", path]

        proc = subprocess.Popen(
            cmd,
            cwd=bot_dir,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True
        )

        RUNNING_PROCESSES[bot_id] = {
            "process": proc,
            "log_file_obj": log_file,
            "log_path": log_path,
            "last_crash_notify": 0
        }

        binfo["status"] = "RUNNING"
        binfo["start_time"] = time.time()
        save_bots(bots)
        return True
    except Exception as e:
        logger.error(f"Failed to start bot {bot_id}: {e}")
        log_file.close()
        return False

def stop_bot_process(bot_id: str) -> bool:
    if bot_id in RUNNING_PROCESSES:
        item = RUNNING_PROCESSES[bot_id]
        p = item["process"]
        if p.poll() is None:
            p.terminate()
            try:
                p.wait(timeout=2)
            except subprocess.TimeoutExpired:
                p.kill()
        try:
            item["log_file_obj"].close()
        except Exception:
            pass
        del RUNNING_PROCESSES[bot_id]

    bots = get_bots()
    if bot_id in bots:
        bots[bot_id]["status"] = "STOPPED"
        bots[bot_id]["start_time"] = None
        save_bots(bots)
    return True

def get_bot_resource_usage(bot_id: str) -> tuple:
    if bot_id in RUNNING_PROCESSES:
        p = RUNNING_PROCESSES[bot_id]["process"]
        if p.poll() is None:
            try:
                ps = psutil.Process(p.pid)
                cpu = ps.cpu_percent(interval=0.05)
                mem = ps.memory_info().rss / (1024 * 1024)
                return round(cpu, 1), round(mem, 1)
            except Exception:
                pass
    return 0.0, 0.0

async def auto_fix_guardian_task(app: Application):
    while True:
        try:
            bots = get_bots()
            users = get_users()
            now = time.time()

            for bot_id, binfo in list(bots.items()):
                owner_id = str(binfo.get("owner_id"))
                if owner_id in users and users[owner_id].get("restricted", False):
                    if binfo.get("status") == "RUNNING":
                        stop_bot_process(bot_id)
                    continue

                if binfo.get("status") == "RUNNING" and binfo.get("autofix", True):
                    if bot_id in RUNNING_PROCESSES:
                        proc = RUNNING_PROCESSES[bot_id]["process"]
                        if proc.poll() is not None:
                            crash_count = binfo.get("crash_count", 0) + 1
                            binfo["crash_count"] = crash_count
                            save_bots(bots)

                            log_path = RUNNING_PROCESSES[bot_id]["log_path"]
                            
                            if crash_count >= 3:
                                stop_bot_process(bot_id)
                                bot_path = binfo.get("path")
                                if os.path.exists(bot_path):
                                    try:
                                        os.remove(bot_path)
                                    except Exception:
                                        pass
                                del bots[bot_id]
                                save_bots(bots)
                                
                                try:
                                    await app.bot.send_message(
                                        chat_id=int(owner_id),
                                        text=f"⚠️ **Severe Crash Limit Reached!**\nYour Bot #{bot_id} crashed 3 times repeatedly. It has been permanently terminated and files removed."
                                    )
                                except Exception:
                                    pass
                                continue

                            missing_module = None
                            if os.path.exists(log_path):
                                with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                                    content = lf.read()
                                    match = re.search(r"No module named ['\"]([^'\"]+)['\"]", content)
                                    if match:
                                        missing_module = match.group(1)

                            if missing_module:
                                logger.info(f"Auto-Fixing bot #{bot_id}: Installing {missing_module}")
                                subprocess.run([sys.executable, "-m", "pip", "install", missing_module], capture_output=True)

                            start_bot_process(bot_id)

                            u_info = users.get(owner_id, {})
                            if owner_id and u_info.get("crash_alerts", True):
                                safe_name = str(binfo['name']).replace("_", "\\_")
                                msg = f"⚠️ Crash Alert (#{crash_count}/3)\nYour Bot #{bot_id} ({safe_name}) crashed."
                                if missing_module:
                                    msg += f"\nAuto-installed missing module: {missing_module}."
                                msg += "\nBot automatically restarted!"
                                try:
                                    await app.bot.send_message(chat_id=int(owner_id), text=msg)
                                except Exception:
                                    pass
            await asyncio.sleep(10)
        except Exception as e:
            logger.error(f"Error in Auto-Fix Task: {e}")
            await asyncio.sleep(10)

# ==================== KEYBOARDS ====================

def main_menu_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🚀 Host New Bot", callback_data="menu_host")],
        [InlineKeyboardButton("🤖 My Bots", callback_data="menu_mybots"), InlineKeyboardButton("📁 File Manager", callback_data="menu_files")],
        [InlineKeyboardButton("📊 Dashboard", callback_data="menu_dashboard"), InlineKeyboardButton("🎁 Refer & Earn", callback_data="menu_referral")],
        [InlineKeyboardButton("🎟️ Redeem Code", callback_data="menu_redeem_prompt"), InlineKeyboardButton("⚙️ Settings", callback_data="menu_settings")],
        [InlineKeyboardButton("💾 Backup Data", callback_data="menu_backup"), InlineKeyboardButton("👤 My Account", callback_data="menu_account")],
        [InlineKeyboardButton("📢 Official Channel ↗", url=OFFICIAL_CHANNEL_URL), InlineKeyboardButton("👨‍💻 Contact Owner ↗", url="https://t.me/Rolax112")]
    ]
    return InlineKeyboardMarkup(keyboard)

def host_options_keyboard() -> InlineKeyboardMarkup:
    keyboard = [
        [InlineKeyboardButton("🐍 Upload Python Script (.py)", callback_data="upload_py")],
        [InlineKeyboardButton("🟨 Upload JS Script (.js)", callback_data="upload_js")],
        [InlineKeyboardButton("🐙 Deploy from GitHub Repo", callback_data="upload_github")],
        [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_start")]
    ]
    return InlineKeyboardMarkup(keyboard)

def admin_panel_keyboard(user_id: int) -> InlineKeyboardMarkup:
    config = get_config()
    bot_status = config.get("bot_status", "ON")
    m_mode = "ON 🟡" if config.get("maintenance_mode", False) else "OFF 🟢"
    rem_status = "ON 🟢" if config.get("daily_reminder_active", True) else "OFF 🔴"
    
    if int(user_id) == int(ADMIN_ID):
        keyboard = [
            [InlineKeyboardButton(f"🤖 System: {bot_status}", callback_data="adm_toggle_status"), InlineKeyboardButton(f"🛠️ Maint: {m_mode}", callback_data="adm_toggle_maint")],
            [InlineKeyboardButton("🏆 Top Users", callback_data="adm_top_users"), InlineKeyboardButton("📈 Analytics", callback_data="adm_user_analytics")],
            [InlineKeyboardButton("👑 All Admins", callback_data="adm_all_admins"), InlineKeyboardButton("📝 Changelogs", callback_data="adm_changelogs")],
            [InlineKeyboardButton("👆 User Clicks", callback_data="adm_user_clicks"), InlineKeyboardButton("✉️ DM User", callback_data="adm_dm_user")],
            [InlineKeyboardButton(f"⏰ Daily Reminder: {rem_status}", callback_data="adm_toggle_reminder")],
            [InlineKeyboardButton("➕ Add Credit", callback_data="adm_add_credit"), InlineKeyboardButton("➖ Remove Credit", callback_data="adm_rem_credit")],
            [InlineKeyboardButton("🎁 Set Referral", callback_data="adm_set_ref_reward"), InlineKeyboardButton("🎟️ Create Redeem", callback_data="adm_create_redeem")],
            [InlineKeyboardButton("📢 Instant Broadcast", callback_data="adm_broadcast"), InlineKeyboardButton("🖼️ Media Broadcast", callback_data="adm_broadcast_media")],
            [InlineKeyboardButton("⏰ Schedule Announce", callback_data="adm_schedule_announcement")],
            [InlineKeyboardButton("📥 Download DB", callback_data="adm_download_backup"), InlineKeyboardButton("📤 Restore DB", callback_data="adm_restore_backup")],
            [InlineKeyboardButton("👥 User Management", callback_data="adm_user_mgmt"), InlineKeyboardButton("👤 View Profile", callback_data="adm_view_user")],
            [InlineKeyboardButton("🚫 Ban User", callback_data="adm_ban"), InlineKeyboardButton("✅ Unban User", callback_data="adm_unban")],
            [InlineKeyboardButton("🔒 Restrict User", callback_data="adm_restrict_user"), InlineKeyboardButton("🔓 Unrestrict User", callback_data="adm_unrestrict_user")],
            [InlineKeyboardButton("🛑 Stop Any Bot", callback_data="adm_stop_any_bot"), InlineKeyboardButton("🗑️ Delete Any Bot", callback_data="adm_del_any_bot")],
            [InlineKeyboardButton("💎 Give Premium", callback_data="adm_give_premium"), InlineKeyboardButton("❌ Remove Premium", callback_data="adm_rem_premium")],
            [InlineKeyboardButton("📢 Force Join", callback_data="adm_force_join"), InlineKeyboardButton("💻 Server Monitor", callback_data="adm_vps_monitor")],
            [InlineKeyboardButton("➕ Add Admin", callback_data="adm_add_admin"), InlineKeyboardButton("➖ Remove Admin", callback_data="adm_remove_admin")],
            [InlineKeyboardButton("📁 Hosted Files", callback_data="adm_all_files"), InlineKeyboardButton("📋 Audit Logs", callback_data="adm_audit_logs")],
            [InlineKeyboardButton("🔍 DB Query", callback_data="adm_db_query"), InlineKeyboardButton("☁️ Cloud Backup", callback_data="adm_cloud_backup")],
            [InlineKeyboardButton("🧹 Clear Logs", callback_data="adm_clean_cache"), InlineKeyboardButton("📜 Live Logs", callback_data="adm_live_logs")],
            [InlineKeyboardButton("⚡ RAM/CPU Limits", callback_data="adm_resource_limits"), InlineKeyboardButton("🔔 Pending Requests", callback_data="adm_pending")],
            [InlineKeyboardButton("📊 Stats", callback_data="adm_stats"), InlineKeyboardButton("📋 Session Logs", callback_data="adm_session_logs")],
            [InlineKeyboardButton("⛔ Stop All Bots", callback_data="adm_stop_all"), InlineKeyboardButton("🔄 Restart All", callback_data="adm_restart_all")]
        ]
    else:
        keyboard = [
            [InlineKeyboardButton("👑 All Admins", callback_data="adm_all_admins"), InlineKeyboardButton("📝 Changelogs", callback_data="adm_changelogs")],
            [InlineKeyboardButton("👆 User Clicks", callback_data="adm_user_clicks"), InlineKeyboardButton("⚡ RAM/CPU Limits", callback_data="adm_resource_limits")],
            [InlineKeyboardButton("🧹 Clear Logs", callback_data="adm_clean_cache"), InlineKeyboardButton("📜 Live Logs", callback_data="adm_live_logs")],
            [InlineKeyboardButton("📊 Stats", callback_data="adm_stats"), InlineKeyboardButton("💎 Give Premium", callback_data="adm_give_premium")],
            [InlineKeyboardButton("📋 Session Logs", callback_data="adm_session_logs"), InlineKeyboardButton("💻 Server Monitor", callback_data="adm_vps_monitor")],
            [InlineKeyboardButton("📋 Audit Logs", callback_data="adm_audit_logs")]
        ]
    return InlineKeyboardMarkup(keyboard)

# ==================== HELPERS ====================

def get_start_text(user_first_name: str, user_bot_count: int, max_bots: int, is_premium: bool, credits: float, expiry_str: str = "") -> str:
    plan_name = f"Premium VIP (Infinity Host){expiry_str}" if is_premium else f"Free Member (Max Bots: {max_bots})"
    return (
        f"✨ **EXCLUSIVE ROLAX HOSTING V2** ✨\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👋 Hello **{user_first_name}**, Welcome!\n\n"
        f"⚡ Here you can host and manage your Python and Node.js bots 24/7 without interruption.\n\n"
        f"📊 **Account Summary:**\n"
        f"• **Status:** `{plan_name}`\n"
        f"• **Credits:** `{round(credits, 2)} Credits` (1 Credit = 1 Bot Slot)\n"
        f"• **Active Bots:** `{user_bot_count} / {max_bots}`\n"
        f"• **Support:** `{OWNER_USERNAME}`\n\n"
        f"👇 Select an option using the interactive buttons below:"
    )

def register_user(user, referrer_id: Optional[str] = None) -> dict:
    users = get_users()
    uid = str(user.id)
    config = get_config()
    ref_reward = config.get("referral_reward", 0.25)

    if uid not in users:
        users[uid] = {
            "username": user.username or "N/A",
            "name": user.first_name,
            "joined": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "banned": False,
            "restricted": False,
            "premium": False,
            "premium_expiry": None,
            "crash_alerts": True,
            "autofix": True,
            "referred_by": None,
            "credits": 1.0
        }
        if referrer_id and referrer_id != uid and referrer_id in users:
            referred_user_data = users[uid]
            if not referred_user_data.get("referred_by_checked"):
                users[uid]["referred_by"] = referrer_id
                users[uid]["referred_by_checked"] = True
                users[referrer_id]["credits"] = users[referrer_id].get("credits", 1.0) + ref_reward
                log_session_action(int(referrer_id), users[referrer_id].get("username", "N/A"), f"Received referral bonus (+{ref_reward}) from User {uid}")
        log_session_action(user.id, user.username or "N/A", "New User Registered")
    else:
        users[uid]["username"] = user.username or "N/A"
        users[uid]["name"] = user.first_name
        if "credits" not in users[uid]:
            users[uid]["credits"] = 1.0
        if "restricted" not in users[uid]:
            users[uid]["restricted"] = False
        if "premium_expiry" not in users[uid]:
            users[uid]["premium_expiry"] = None
        log_session_action(user.id, user.username or "N/A", "User Session Started / /start")
            
    save_users(users)
    return users[uid]

def get_user_max_bots(user_id: int) -> int:
    users = get_users()
    u_data = users.get(str(user_id), {})
    if u_data.get("premium", False):
        return 999999
    credits = u_data.get("credits", 1.0)
    return max(1, int(credits))

# ==================== COMMAND HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args
    referrer_id = args[0] if args and args[0].isdigit() else None

    u_data = register_user(user, referrer_id)

    if u_data.get("banned", False):
        await update.message.reply_text("Access Denied: You are banned from using this hosting bot.")
        return

    if u_data.get("restricted", False):
        await update.message.reply_text("⚠️ **Account Restricted:** Your hosting capabilities have been restricted by the administrator.")
        return

    if not await check_force_join(user.id, context.bot):
        buttons = [[InlineKeyboardButton("📢 Join Official Channel", url=OFFICIAL_CHANNEL_URL)]]
        buttons.append([InlineKeyboardButton("🔄 Verify Membership", callback_data="menu_start")])
        await update.message.reply_text(
            "Force Join Required\n\nPlease join our official channel to use bot hosting features:",
            reply_markup=InlineKeyboardMarkup(buttons)
        )
        return

    config = get_config()
    if config.get("bot_status") == "OFF" and not is_admin(user.id):
        await update.message.reply_text("EXCLUSIVE ROLAX HOSTING V2 is currently offline for maintenance by @Rolax112.")
        return

    if config.get("maintenance_mode", False) and not is_admin(user.id):
        await update.message.reply_text("System is undergoing scheduled maintenance. Please check back shortly.")
        return

    bots = get_bots()
    user_bot_count = sum(1 for b in bots.values() if b.get("owner_id") == user.id)
    max_bots = get_user_max_bots(user.id)
    is_prem = u_data.get("premium", False)
    credits = u_data.get("credits", 1.0)
    
    expiry_str = ""
    if is_prem and u_data.get("premium_expiry"):
        rem_secs = u_data["premium_expiry"] - time.time()
        if rem_secs > 0:
            days = int(rem_secs // 86400)
            hours = int((rem_secs % 86400) // 3600)
            expiry_str = f" (Expires in {days}d {hours}h)"

    await update.message.reply_text(
        get_start_text(user.first_name, user_bot_count, max_bots, is_prem, credits, expiry_str),
        parse_mode="Markdown",
        reply_markup=main_menu_keyboard()
    )

async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /redeem <code>")
        return

    code = args[0].strip()
    codes = get_redeem_codes()
    users = get_users()
    uid = str(user.id)

    if code not in codes:
        await update.message.reply_text("Invalid or expired redeem code.")
        return

    cinfo = codes[code]
    if cinfo.get("used", False):
        await update.message.reply_text("This redeem code has already been used or expired.")
        return

    max_limit = cinfo.get("max_uses", 1)
    redeemed_list = cinfo.get("redeemed_by_users", [])
    if uid in redeemed_list:
        await update.message.reply_text("You have already used this redeem code!")
        return

    if len(redeemed_list) >= max_limit:
        cinfo["used"] = True
        save_redeem_codes(codes)
        await update.message.reply_text("This redeem code has reached its maximum usage limit.")
        return

    if cinfo.get("expiry_time") and time.time() >= cinfo["expiry_time"]:
        cinfo["used"] = True
        save_redeem_codes(codes)
        await update.message.reply_text("This redeem code has expired.")
        return

    reward_credits = cinfo["credits"]
    users[uid]["credits"] = users[uid].get("credits", 1.0) + reward_credits
    
    redeemed_list.append(uid)
    cinfo["redeemed_by_users"] = redeemed_list
    if len(redeemed_list) >= max_limit:
        cinfo["used"] = True

    save_users(users)
    save_redeem_codes(codes)

    log_audit_action(f"User {user.id} redeemed code {code} for {reward_credits} credits", user.id)
    log_session_action(user.id, user.username or "N/A", f"Redeemed code {code} for {reward_credits} credits")
    await update.message.reply_text(f"Redeem Successful!\n\nAdded +{reward_credits} Credits to your account wallet. Enjoy hosting!")

async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("You are not authorized to use the admin panel.")
        return

    users = get_users()
    bots = get_bots()
    config = get_config()

    vps_mem = psutil.virtual_memory()
    vps_cpu = psutil.cpu_percent(interval=None)

    role_title = "SUPER ADMIN" if int(user.id) == int(ADMIN_ID) else "SUB-ADMIN"

    text = (
        f"EXCLUSIVE ROLAX {role_title} CONTROL CENTER v3.18\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"Administrator: @{user.username or user.id} (ID: {user.id})\n"
        f"Registered Users: {len(users)}\n"
        f"Total Deployed Bots: {len(bots)}\n"
        f"Active Running Bots: {sum(1 for b in bots.values() if b.get('status') == 'RUNNING')}\n"
        f"Referral Reward Rate: {config.get('referral_reward', 0.25)} Credits\n"
        f"Core System Status: {config.get('bot_status', 'ON')}\n\n"
        f"Dedicated Server Metrics:\n"
        f"RAM Utilization: {round(vps_mem.used / (1024**3), 2)} GB / {round(vps_mem.total / (1024**3), 2)} GB ({vps_mem.percent}%)\n"
        f"CPU Load Average: {vps_cpu}%"
    )

    if update.message:
        await update.message.reply_text(text, reply_markup=admin_panel_keyboard(user.id))
    elif update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=admin_panel_keyboard(user.id))

async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if int(user.id) != int(ADMIN_ID):
        await update.message.reply_text("Only Super Owner can add new admins.")
        return

    args = context.args
    if not args:
        await update.message.reply_text("Usage: /addadmin <user_chat_id>")
        return

    try:
        new_adm_id = int(args[0])
        admins = get_admins()
        if new_adm_id not in admins:
            admins.append(new_adm_id)
            save_admins(admins)
            log_audit_action(f"Added Sub-Admin via command: {new_adm_id}", user.id)
            await update.message.reply_text(f"User {new_adm_id} has been successfully added as a Sub-Admin!")
            try:
                await context.bot.send_message(new_adm_id, "Congratulations!\nYou have been promoted to Sub-Admin by the owner. Send /admin to open your secured admin panel.")
            except Exception:
                pass
        else:
            await update.message.reply_text("This user is already an admin.")
    except ValueError:
        await update.message.reply_text("Invalid Chat ID. Provide numbers only.")

async def add_premium_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_admin(user.id):
        return

    args = context.args
    if len(args) < 2:
        await update.message.reply_text("Usage: /addpremium <user_chat_id> <days>\nExample: /addpremium 8472327599 30")
        return

    try:
        target_uid = str(int(args[0]))
        days = int(args[1])
        users = get_users()
        
        if target_uid in users:
            expiry_timestamp = time.time() + (days * 86400)
            users[target_uid]["premium"] = True
            users[target_uid]["premium_expiry"] = expiry_timestamp
            save_users(users)
            
            log_audit_action(f"Granted Premium VIP status to User ID {target_uid} for {days} days", user.id)
            await update.message.reply_text(f"Success! User {target_uid} has been upgraded to Premium VIP for {days} Days.")
            try:
                await context.bot.send_message(int(target_uid), f"Congratulations!\nYou have been upgraded to Premium VIP for {days} Days by Admin! 🚀")
            except Exception:
                pass
        else:
            await update.message.reply_text("User ID not found in database.")
    except ValueError:
        await update.message.reply_text("Invalid format. Provide numbers only for User ID and Days.")

# ==================== CALLBACK ROUTER ====================

async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = query.from_user
    data = query.data

    log_button_click(user.id, user.username or "N/A", data)

    users = get_users()
    u_data = users.get(str(user.id), {})

    if u_data.get("banned", False):
        await query.answer("Access Denied: You are banned.", show_alert=True)
        return

    if u_data.get("restricted", False):
        await query.answer("Access Denied: Your account is restricted.", show_alert=True)
        return

    # Admins must retain access to the admin panel even if force-join
    # configuration or Telegram membership checks fail. Regular users must
    # still pass the force-join check.
    if not is_admin(user.id) and data != "menu_start":
        if not await check_force_join(user.id, context.bot):
            await query.answer("Please join our required channels first!", show_alert=True)
            return

    config = get_config()
    if config.get("bot_status") == "OFF" and not is_admin(user.id):
        await query.answer("Bot is currently offline.", show_alert=True)
        return

    if config.get("maintenance_mode", False) and not is_admin(user.id):
        await query.answer("System is under maintenance mode.", show_alert=True)
        return

    await query.answer()

    if data == "menu_start":
        if not await check_force_join(user.id, context.bot):
            buttons = [[InlineKeyboardButton("📢 Join Official Channel", url=OFFICIAL_CHANNEL_URL)]]
            buttons.append([InlineKeyboardButton("🔄 Verify Membership", callback_data="menu_start")])
            await query.edit_message_text(
                "Force Join Required\n\nPlease join our official channel to proceed:",
                reply_markup=InlineKeyboardMarkup(buttons)
            )
            return
        bots = get_bots()
        user_bot_count = sum(1 for b in bots.values() if b.get("owner_id") == user.id)
        max_bots = get_user_max_bots(user.id)
        is_prem = u_data.get("premium", False)
        credits = u_data.get("credits", 1.0)
        
        expiry_str = ""
        if is_prem and u_data.get("premium_expiry"):
            rem_secs = u_data["premium_expiry"] - time.time()
            if rem_secs > 0:
                days = int(rem_secs // 86400)
                hours = int((rem_secs % 86400) // 3600)
                expiry_str = f" (Expires in {days}d {hours}h)"

        log_session_action(user.id, user.username or "N/A", "Navigated to Main Menu")
        await query.edit_message_text(get_start_text(user.first_name, user_bot_count, max_bots, is_prem, credits, expiry_str), parse_mode="Markdown", reply_markup=main_menu_keyboard())

    elif data == "menu_referral":
        bot_username = context.bot.username
        ref_link = f"https://t.me/{bot_username}?start={user.id}"
        config = get_config()
        ref_reward = config.get("referral_reward", 0.25)
        credits = u_data.get("credits", 1.0)

        referred_count = sum(1 for u in users.values() if str(u.get("referred_by")) == str(user.id))

        text = (
            f"🎁 **Refer & Earn Credits**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"🔗 Your Unique Referral Link:\n`{ref_link}`\n\n"
            f"📌 **Rule:** For every 1 successful invite you get **+{ref_reward} Credits**!\n"
            f"👥 **Total Referred Users:** `{referred_count}`\n"
            f"💡 **1 Credit** = **1 Bot Host Slot**\n\n"
            f"📊 **Your Wallet:** `{round(credits, 2)} Credits`\n\n"
            f"Share the link with your friends and expand your free hosting slots!"
        )
        keyboard = [
            [InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={ref_link}&text=🚀%20Host%20your%20Python%20and%20Node.js%20bots%2024/7%20for%20FREE%20on%20Exclusive%20Rolax%20Hosting!")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_start")]
        ]
        log_session_action(user.id, user.username or "N/A", "Opened Referral Menu")
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "menu_redeem_prompt":
        context.user_data["expecting_redeem_code"] = True
        await query.edit_message_text(
            "🎟️ Redeem Gift Code\n\nPlease send your redeem code in chat (e.g. ROLAX2026):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_start")]])
        )

    elif data == "menu_host":
        text = f"🚀 Deploy New Script\n\nChoose your preferred deployment vector below:\n\nPowered by {OWNER_USERNAME}"
        await query.edit_message_text(text, reply_markup=host_options_keyboard())

    elif data in ["upload_py", "upload_js"]:
        ext = ".py" if data == "upload_py" else ".js"
        context.user_data["expecting_file_type"] = ext
        await query.edit_message_text(
            f"📤 Please upload your {ext} script file as a document attachment.\n\n{OWNER_USERNAME}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_host")]])
        )

    elif data == "upload_github":
        context.user_data["expecting_github"] = True
        await query.edit_message_text(
            f"🐙 Send your public GitHub Repository Clone URL (e.g., https://github.com/user/repo):\n\n{OWNER_USERNAME}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_host")]])
        )

    elif data == "menu_mybots":
        bots = get_bots()
        user_bots = {bid: b for bid, b in bots.items() if b.get("owner_id") == user.id}
        total = len(user_bots)
        running = sum(1 for b in user_bots.values() if b.get("status") == "RUNNING")
        stopped = total - running

        if total == 0:
            text = (
                f"🤖 Your Hosted Applications\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"No active deployments found.\n\n"
                f"Click \"Host New Bot\" to upload your source code or link a GitHub repository!\n\n"
                f"{OWNER_USERNAME}"
            )
            keyboard = [
                [InlineKeyboardButton("🚀 Host New Bot", callback_data="menu_host")],
                [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_start")]
            ]
        else:
            text = (
                f"🤖 Active Bots Fleet Management\n"
                f"Total Deployed: {total} | Running: {running} | Stopped: {stopped}\n\n"
                f"Select an application to access controls:\n\n"
                f"{OWNER_USERNAME}"
            )
            keyboard = []
            for bid, binfo in user_bots.items():
                status_icon = "🟢" if binfo.get("status") == "RUNNING" else "🔴"
                keyboard.append([InlineKeyboardButton(f"🤖 {binfo['name']} [{binfo.get('runtime', 'python')}] {status_icon}", callback_data=f"bot_control_{bid}")])

            keyboard.append([InlineKeyboardButton("🚀 Host New Bot", callback_data="menu_host")])
            keyboard.append([InlineKeyboardButton("📊 Dashboard", callback_data="menu_dashboard"), InlineKeyboardButton("🔙 Main Menu", callback_data="menu_start")])

        log_session_action(user.id, user.username or "N/A", "Viewed My Bots Fleet")
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("bot_control_"):
        bot_id = data.split("_")[2]
        bots = get_bots()
        binfo = bots.get(bot_id)

        if not binfo or binfo.get("owner_id") != user.id:
            await query.answer("Bot instance not found or unauthorized.", show_alert=True)
            return

        status = binfo.get("status", "STOPPED")
        status_text = "RUNNING 🟢" if status == "RUNNING" else "STOPPED 🔴"
        
        uptime_str = "0m"
        if status == "RUNNING" and binfo.get("start_time"):
            elapsed = int(time.time() - binfo["start_time"])
            mins, secs = divmod(elapsed, 60)
            hours, mins = divmod(mins, 60)
            uptime_str = f"{hours}h {mins}m {secs}s" if hours else f"{mins}m {secs}s"

        autofix_state = "ON 🟢" if binfo.get("autofix", True) else "OFF 🔴"

        text = (
            f"⚡ Application Control Terminal\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Name: {binfo['name']}\n"
            f"Instance ID: #{bot_id}\n"
            f"Operational State: {status_text}\n"
            f"Uptime Session: {uptime_str}\n"
            f"Runtime Engine: {binfo.get('runtime', 'python')}\n"
            f"Vector Source: {binfo.get('source', 'upload')}\n"
            f"Deployment Date: {binfo.get('deployed', 'N/A')}\n\n"
            f"Select management tool below:"
        )

        keyboard = [
            [InlineKeyboardButton("🔄 Restart Instance", callback_data=f"bot_act_restart_{bot_id}"), InlineKeyboardButton("⏹️ Terminate", callback_data=f"bot_act_stop_{bot_id}")],
            [InlineKeyboardButton("🔑 Environment Variables (.env)", callback_data=f"bot_act_env_{bot_id}"), InlineKeyboardButton("📜 Live Stdout Logs", callback_data=f"bot_act_logs_{bot_id}")],
            [InlineKeyboardButton("📊 Telemetry Stats", callback_data=f"bot_act_stats_{bot_id}"), InlineKeyboardButton(f"🤖 Auto-Fixer: {autofix_state}", callback_data=f"bot_act_autofix_{bot_id}")],
            [InlineKeyboardButton("📁 Project Files", callback_data=f"bot_act_files_{bot_id}"), InlineKeyboardButton("💾 Backup Source", callback_data="menu_backup")],
            [InlineKeyboardButton("🗑️ Purge & Delete", callback_data=f"bot_act_delete_{bot_id}")],
            [InlineKeyboardButton("🔙 Back to Fleet", callback_data="menu_mybots")]
        ]

        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("bot_act_"):
        parts = data.split("_")
        action = parts[2]
        bot_id = parts[3]
        bots = get_bots()
        binfo = bots.get(bot_id)

        if not binfo or binfo.get("owner_id") != user.id:
            await query.answer("Instance unavailable.", show_alert=True)
            return

        if action == "restart":
            start_bot_process(bot_id)
            log_session_action(user.id, user.username or "N/A", f"Restarted Bot #{bot_id}")
            await query.answer("Application successfully restarted!", show_alert=True)
            query.data = f"bot_control_{bot_id}"
            await callback_query_handler(update, context)

        elif action == "stop":
            stop_bot_process(bot_id)
            log_session_action(user.id, user.username or "N/A", f"Stopped Bot #{bot_id}")
            await query.answer("Application stopped.", show_alert=True)
            query.data = f"bot_control_{bot_id}"
            await callback_query_handler(update, context)

        elif action == "delete":
            stop_bot_process(bot_id)
            if os.path.exists(binfo["path"]):
                try:
                    os.remove(binfo["path"])
                except Exception:
                    pass
            del bots[bot_id]
            save_bots(bots)
            log_session_action(user.id, user.username or "N/A", f"Deleted Bot #{bot_id}")
            await query.answer("Application purged completely.", show_alert=True)
            query.data = "menu_mybots"
            await callback_query_handler(update, context)

        elif action == "stats":
            cpu, ram = get_bot_resource_usage(bot_id)
            await query.answer(f"Real-time Metrics:\nCPU Load: {cpu}%\nRAM Consumption: {ram} MB", show_alert=True)

        elif action == "logs":
            log_path = os.path.join(LOGS_DIR, f"bot_{bot_id}.log")
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8", errors="ignore") as lf:
                    lines = lf.readlines()[-20:]
                log_content = "".join(lines) or "Log buffer empty."
            else:
                log_content = "No logs recorded yet."
            await query.edit_message_text(
                f"📜 Live Console Output (Last 20 Lines):\n\n{log_content[-3500:]}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Instance", callback_data=f"bot_control_{bot_id}")]])
            )

        elif action == "env":
            context.user_data["editing_env_bot"] = bot_id
            env_path = os.path.join(os.path.dirname(binfo["path"]), ".env")
            curr_env = "None"
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as ef:
                    curr_env = ef.read()
            await query.edit_message_text(
                f"🔑 Environment Configuration (.env)\n\nCurrent Variables:\n{curr_env}\n\nSend new variable in format KEY=VALUE:",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data=f"bot_control_{bot_id}")]])
            )

        elif action == "autofix":
            binfo["autofix"] = not binfo.get("autofix", True)
            save_bots(bots)
            state_str = "ENABLED 🟢" if binfo["autofix"] else "DISABLED 🔴"
            await query.answer(f"Auto-Fix guardian set to {state_str}", show_alert=True)
            query.data = f"bot_control_{bot_id}"
            await callback_query_handler(update, context)

        elif action == "files":
            bot_dir = os.path.dirname(binfo["path"])
            files_list = os.listdir(bot_dir) if os.path.exists(bot_dir) else []
            f_str = "\n".join([f"📄 {f}" for f in files_list]) or "No additional files."
            await query.edit_message_text(
                f"📁 Directory File Explorer (#{bot_id}):\n\n{f_str}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back to Instance", callback_data=f"bot_control_{bot_id}")]])
            )

    elif data == "menu_files":
        bots = get_bots()
        user_bots = {bid: b for bid, b in bots.items() if b.get("owner_id") == user.id}
        if not user_bots:
            await query.edit_message_text("📁 File Manager\n\nYou have no hosted projects.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="menu_start")]]))
            return

        kb = [[InlineKeyboardButton(f"📁 Files: {b['name']}", callback_data=f"bot_act_files_{bid}")] for bid, b in user_bots.items()]
        kb.append([InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_start")])
        await query.edit_message_text("📁 Project File Manager\n\nSelect a deployed bot workspace:", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "menu_settings":
        u_info = users.get(str(user.id), {})
        ca = "ON 🟢" if u_info.get("crash_alerts", True) else "OFF 🔴"
        af = "ON 🟢" if u_info.get("autofix", True) else "OFF 🔴"

        text = f"⚙️ User Preferences & Controls\n\n🔔 Crash Notification Alerts: {ca}\n🤖 Auto-Fix Guardian: {af}"
        keyboard = [
            [InlineKeyboardButton(f"🔔 Crash Alerts: {ca}", callback_data="toggle_setting_ca")],
            [InlineKeyboardButton(f"🤖 Auto-Fix: {af}", callback_data="toggle_setting_af")],
            [InlineKeyboardButton("👤 View My Profile", callback_data="menu_account")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_start")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("toggle_setting_"):
        stype = data.split("_")[2]
        u_info = users.get(str(user.id), {})
        if stype == "ca":
            u_info["crash_alerts"] = not u_info.get("crash_alerts", True)
        elif stype == "af":
            u_info["autofix"] = not u_info.get("autofix", True)
        save_users(users)
        query.data = "menu_settings"
        await callback_query_handler(update, context)

    elif data == "menu_account":
        bots = get_bots()
        user_bots_count = sum(1 for b in bots.values() if b.get("owner_id") == user.id)
        max_bots = get_user_max_bots(user.id)
        is_prem = u_data.get("premium", False)
        plan_str = "Premium VIP (Infinity Host)" if is_prem else f"Free Member (Max Bots: {max_bots})"
        credits = u_data.get("credits", 1.0)
        cfg = get_config()
        text = (
            f"👤 Account Profile Matrix\n\n"
            f"🆔 Telegram Chat ID: {user.id}\n"
            f"🏷️ Username: @{user.username or 'N/A'}\n"
            f"💎 Current Membership: {plan_str}\n"
            f"💰 Wallet Credits: {round(credits, 2)} Credits\n\n"
            f"📊 Resource Quota Allocations:\n"
            f"🤖 Deployed Instances: {user_bots_count} / {max_bots}\n"
            f"⚡ CPU Limit Per Core: {cfg.get('default_cpu_limit', 8.0)}\n"
            f"🧠 RAM Limit Cap: {cfg.get('default_ram_limit', 8192)} MB\n"
            f"💾 Cloud Backups: Enabled ✅\n"
            f"🤖 Auto-Fix Engine: Enabled ✅"
        )
        keyboard = [
            [InlineKeyboardButton("🎁 Refer & Earn", callback_data="menu_referral"), InlineKeyboardButton("🎟️ Redeem Code", callback_data="menu_redeem_prompt")],
            [InlineKeyboardButton("🤖 My Fleet", callback_data="menu_mybots"), InlineKeyboardButton("📊 Dashboard", callback_data="menu_dashboard")],
            [InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_start")]
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "menu_dashboard":
        bots = get_bots()
        user_bots = {bid: b for bid, b in bots.items() if b.get("owner_id") == user.id}
        running_cnt = sum(1 for b in user_bots.values() if b.get("status") == "RUNNING")
        stopped_cnt = len(user_bots) - running_cnt

        tot_cpu, tot_ram = 0.0, 0.0
        bots_info_str = ""

        for bid, binfo in user_bots.items():
            cpu, ram = get_bot_resource_usage(bid)
            tot_cpu += cpu
            tot_ram += ram
            status_desc = f"CPU: {cpu}% | RAM: {ram} MB | State: " + ("Running 🟢" if binfo.get("status") == "RUNNING" else "Stopped 🔴")
            bots_info_str += f"\n\n🤖 {binfo['name']} (#{bid})\n└ {status_desc}"

        if not user_bots:
            bots_info_str = "\n\nHosted Applications: None"

        is_prem = u_data.get("premium", False)
        plan_str = "Premium VIP" if is_prem else "Free Member"
        text = (
            f"📊 Live Telemetry Dashboard\n\n"
            f"💎 Plan Tier: {plan_str} | Bots: {len(user_bots)}\n"
            f"🟢 Active: {running_cnt} | 🔴 Inactive: {stopped_cnt}\n"
            f"⚡ Aggregate CPU Utilization: {round(tot_cpu, 1)}%\n"
            f"🧠 Aggregate RAM Consumption: {round(tot_ram, 1)} MB"
            f"{bots_info_str}"
        )
        keyboard = [[InlineKeyboardButton("🔙 Back to Main Menu", callback_data="menu_start")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "menu_backup":
        user_dir = os.path.join(HOSTED_DIR, str(user.id))
        if not os.path.exists(user_dir) or not os.listdir(user_dir):
            await query.answer("No workspace files found to archive.", show_alert=True)
            return

        zip_path = os.path.join(BASE_DIR, f"backup_{user.id}")
        archive_file = shutil.make_archive(zip_path, 'zip', user_dir)

        with open(archive_file, 'rb') as f:
            await context.bot.send_document(
                chat_id=user.id,
                document=f,
                filename=f"ROLAX_WORKSPACE_BACKUP_{user.id}.zip",
                caption="💾 Here is your secure project source archive backup."
            )
        if os.path.exists(archive_file):
            os.remove(archive_file)
        await query.answer("Backup archive dispatched to chat!", show_alert=True)

    # ==================== ADMIN ACTIONS ====================

    elif data == "adm_all_admins" and is_admin(user.id):
        admins = get_admins()
        admin_lines = []
        for aid in admins:
            role = "👑 Super Owner" if aid == ADMIN_ID else "🛡️ Sub-Admin"
            admin_lines.append(f"• ID: `{aid}` | {role}")
        text = "👑 ALL ADMINS LIST:\n\n" + ("\n".join(admin_lines) if admin_lines else "No admins found.")
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_changelogs" and is_admin(user.id):
        changelog_text = (
            "📝 ADMIN PANEL CHANGELOGS & UPDATES (v3.18):\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "• Added 'Stop Any Bot' and 'Delete Any Bot' options for complete admin control.\n"
            "• Added User Restrict/Unrestrict feature.\n"
            "• Implemented 3-times auto-crash limit with automatic bot termination & file deletion.\n"
            "• Optimized all admin side-by-side button grids."
        )
        await query.edit_message_text(changelog_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_user_clicks" and is_admin(user.id):
        click_content = "No button clicks recorded yet."
        if os.path.exists(BUTTON_CLICK_LOG_FILE):
            with open(BUTTON_CLICK_LOG_FILE, "r", encoding="utf-8") as f:
                click_content = f.read()[-3500:]
        await query.edit_message_text(
            f"👆 User Button Activity Logs:\n\n{click_content}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_top_users" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        users = get_users()
        sorted_users = sorted(users.items(), key=lambda x: x[1].get("credits", 1.0), reverse=True)
        top_lines = []
        for rank, (uid, uinfo) in enumerate(sorted_users[:15], start=1):
            name = uinfo.get("name", "N/A")
            username = uinfo.get("username", "N/A")
            credits = round(uinfo.get("credits", 1.0), 2)
            top_lines.append(f"{rank}. {name} (@{username}) | ID: {uid} | 💰 {credits} Credits")
        text = "🏆 TOP USERS LEADERBOARD (By Credits):\n\n" + ("\n".join(top_lines) if top_lines else "No users found.")
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_user_analytics" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        users = get_users()
        bots = get_bots()
        lines = []
        for uid, uinfo in list(users.items())[:20]:
            ubot_cnt = sum(1 for b in bots.values() if b.get("owner_id") == int(uid))
            joined_date = uinfo.get("joined", "N/A")
            credits = round(uinfo.get("credits", 1.0), 2)
            lines.append(f"📈 @{uinfo.get('username', 'N/A')}\n   └ ID: {uid} | Bots: {ubot_cnt} | Credits: {credits} | Joined: {joined_date}")
        text = "📈 USER ACTIVITY ANALYTICS & CHAT IDs:\n\n" + ("\n\n".join(lines) if lines else "No analytics data.")
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_dm_user" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_dm_user"] = True
        await query.edit_message_text(
            "✉️ Direct Message User\n\nSend format: USER_ID MESSAGE\nExample: 8472327599 Hello, your bot is running fine!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]])
        )

    elif data == "adm_toggle_reminder" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        cfg = get_config()
        cfg["daily_reminder_active"] = not cfg.get("daily_reminder_active", True)
        save_config(cfg)
        status_msg = "ENABLED 🟢" if cfg["daily_reminder_active"] else "DISABLED 🔴"
        log_audit_action(f"Toggled Daily Reminder to {status_msg}", user.id)
        await query.answer(f"Daily Reminder is now {status_msg}", show_alert=True)
        await admin_command(update, context)

    elif data == "adm_toggle_status" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        cfg = get_config()
        cfg["bot_status"] = "OFF" if cfg.get("bot_status") == "ON" else "ON"
        save_config(cfg)
        log_audit_action(f"Toggled Bot System Status to {cfg['bot_status']}", user.id)
        await query.answer(f"System Status updated to {cfg['bot_status']}", show_alert=True)
        await admin_command(update, context)

    elif data == "adm_toggle_maint" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        cfg = get_config()
        cfg["maintenance_mode"] = not cfg.get("maintenance_mode", False)
        save_config(cfg)
        state_text = "ENABLED" if cfg["maintenance_mode"] else "DISABLED"
        log_audit_action(f"Toggled Maintenance Mode to {state_text}", user.id)
        await query.answer(f"Maintenance Mode is now {state_text}", show_alert=True)
        await admin_command(update, context)

    elif data == "adm_add_credit" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_add_credit"] = True
        await query.edit_message_text(
            "➕ Add Credits to User / All\n\nFormat 1 (Particular User): USER_ID CREDITS\nFormat 2 (All Users): all CREDITS\n\nSend your command below:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]])
        )

    elif data == "adm_rem_credit" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_rem_credit"] = True
        await query.edit_message_text(
            "➖ Remove Credits from User / All\n\nFormat 1: USER_ID CREDITS\nFormat 2: all CREDITS\n\nSend your command below:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]])
        )

    elif data == "adm_set_ref_reward" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_ref_reward"] = True
        cfg = get_config()
        await query.edit_message_text(
            f"🎁 Set Referral Reward Credits\nCurrent reward per referral: {cfg.get('referral_reward', 0.25)}\n\nSend new numeric value:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]])
        )

    elif data == "adm_create_redeem" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_redeem_create"] = True
        await query.edit_message_text(
            "🎟️ Create Redeem Code (With Max Users Limit)\n\n"
            "Format: CODE CREDITS DURATION_DAYS MAX_USERS\n"
            "Example: ROLAX30 5.0 30 100\n\n"
            "Send format below:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]])
        )

    elif data == "adm_download_backup" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        db_files = [USERS_FILE, BOTS_FILE, PENDING_FILE, CONFIG_FILE, ADMINS_FILE, FORCE_JOIN_FILE, REDEEM_FILE]
        zip_path = os.path.join(BASE_DIR, "db_backup_archive")
        temp_dir = os.path.join(BASE_DIR, "temp_db_backup")
        os.makedirs(temp_dir, exist_ok=True)
        for fpath in db_files:
            if os.path.exists(fpath):
                shutil.copy(fpath, temp_dir)
        archive_file = shutil.make_archive(zip_path, 'zip', temp_dir)
        shutil.rmtree(temp_dir)
        with open(archive_file, 'rb') as f:
            await context.bot.send_document(
                chat_id=user.id,
                document=f,
                filename="ROLAX_DATABASE_BACKUP.zip",
                caption="📥 Admin Database Backup File"
            )
        if os.path.exists(archive_file):
            os.remove(archive_file)
        log_audit_action("Downloaded Database Backup via Bot", user.id)
        await query.answer("Database backup sent to chat!", show_alert=True)

    elif data == "adm_restore_backup" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_db_restore"] = True
        await query.edit_message_text(
            "📤 Restore Database Backup\n\nPlease send the .zip backup file containing your database JSON files as a document attachment:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]])
        )

    elif data == "adm_schedule_announcement" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_schedule_announcement"] = True
        await query.edit_message_text(
            "⏰ Announcement Scheduler\n\nFormat: DELAY_MINUTES | MESSAGE\nSend announcement format below:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]])
        )

    elif data == "adm_session_logs" and is_admin(user.id):
        session_content = "No session logs recorded yet."
        if os.path.exists(SESSION_LOG_FILE):
            with open(SESSION_LOG_FILE, "r", encoding="utf-8") as f:
                session_content = f.read()[-3500:]
        await query.edit_message_text(
            f"📋 User Activity Logs & Chat ID Session Manager:\n\n{session_content}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]])
        )

    elif data == "adm_vps_monitor" and is_admin(user.id):
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        cpu = psutil.cpu_percent(interval=0.5)
        text = (
            f"💻 DEDICATED HARDWARE TELEMETRY\n\n"
            f"⚡ CPU Usage: {cpu}%\n"
            f"🧠 System RAM: {round(mem.used / (1024**3), 2)} GB / {round(mem.total / (1024**3), 2)} GB ({mem.percent}%)\n"
            f"💽 Disk Storage: {round(disk.used / (1024**3), 2)} GB / {round(disk.total / (1024**3), 2)} GB ({disk.percent}%)\n"
            f"⚙️ Active OS Processes: {len(psutil.pids())}"
        )
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh Metrics", callback_data="adm_vps_monitor"), InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_broadcast_media" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_media_broadcast"] = True
        await query.edit_message_text("🖼️ Media Broadcast Mode\nSend photo, video, or document with a caption to push broadcast to ALL registered users:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_broadcast" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_broadcast"] = True
        await query.edit_message_text("📢 Global Text Broadcast\nSend broadcast message text below:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_user_mgmt" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        await query.edit_message_text(
            "👥 User Administration Suite\n\nSelect action or input parameters:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚫 Ban User", callback_data="adm_ban"), InlineKeyboardButton("✅ Unban User", callback_data="adm_unban")],
                [InlineKeyboardButton("🔒 Restrict User", callback_data="adm_restrict_user"), InlineKeyboardButton("🔓 Unrestrict User", callback_data="adm_unrestrict_user")],
                [InlineKeyboardButton("🛑 Stop Any Bot", callback_data="adm_stop_any_bot"), InlineKeyboardButton("🗑️ Delete Any Bot", callback_data="adm_del_any_bot")],
                [InlineKeyboardButton("👤 View Profile", callback_data="adm_view_user"), InlineKeyboardButton("💎 Grant Premium", callback_data="adm_give_premium")],
                [InlineKeyboardButton("❌ Remove Premium", callback_data="adm_rem_premium"), InlineKeyboardButton("📋 Users List", callback_data="adm_users_list")],
                [InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]
            ])
        )

    elif data == "adm_view_user" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_view_user"] = True
        await query.edit_message_text("👤 View User Profile\nSend User Chat ID below:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_give_premium" and is_admin(user.id):
        context.user_data["awaiting_give_prem"] = True
        await query.edit_message_text("💎 Grant Timed Premium VIP\nSend format: USER_ID DAYS\nExample: 8472327599 30", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_rem_premium" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_rem_prem"] = True
        await query.edit_message_text("❌ Remove Premium VIP\nSend User Chat ID below:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_restrict_user" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_restrict_id"] = True
        await query.edit_message_text("🔒 Restrict User Hosting & Bots\nSend User ID to restrict and shut down their bots:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_unrestrict_user" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_unrestrict_id"] = True
        await query.edit_message_text("🔓 Unrestrict User\nSend User ID to lift hosting restrictions:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_stop_any_bot" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_stop_bot_id"] = True
        await query.edit_message_text("🛑 Stop Any Hosted Bot\nSend the Bot ID (e.g. 101) to stop it immediately:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_del_any_bot" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_del_bot_id"] = True
        await query.edit_message_text("🗑️ Delete Any Hosted Bot & Files\nSend the Bot ID (e.g. 101) to delete it permanently:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_force_join" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        channels = get_force_join()
        ch_list = "\n".join([f"• {ch}" for ch in channels]) or "No channels configured."
        await query.edit_message_text(
            f"📢 Force Join Configuration\n\nActive Channels:\n{ch_list}\n\nChoose an action:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("➕ Add Channel", callback_data="adm_fj_add"), InlineKeyboardButton("➖ Remove Channel", callback_data="adm_fj_rem")],
                [InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]
            ])
        )

    elif data == "adm_fj_add" and is_admin(user.id):
        context.user_data["awaiting_fj_add"] = True
        await query.edit_message_text("➕ Send channel username or ID to add:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_force_join")]]))

    elif data == "adm_fj_rem" and is_admin(user.id):
        context.user_data["awaiting_fj_rem"] = True
        await query.edit_message_text("➖ Send channel username or ID to remove:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="adm_force_join")]]))

    elif data == "adm_add_admin" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_add_admin"] = True
        await query.edit_message_text("➕ Add Sub-Administrator\nSend Chat ID of the user to grant safe sub-admin rights:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_remove_admin" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_remove_admin"] = True
        admins = get_admins()
        await query.edit_message_text(f"➖ Revoke Admin\nCurrent Admins: {admins}\n\nSend Chat ID to remove:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_users_list" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        all_users = get_users()
        bots = get_bots()
        lines = []
        for uid, uinfo in all_users.items():
            ubot_cnt = sum(1 for b in bots.values() if b.get("owner_id") == int(uid))
            prem_tag = "💎" if uinfo.get("premium") else "🆓"
            restr_tag = " [RESTRICTED 🔒]" if uinfo.get("restricted") else ""
            lines.append(f"{prem_tag} @{uinfo.get('username', 'N/A')} | ID:{uid}{restr_tag} | Bots:{ubot_cnt} | Credits:{round(uinfo.get('credits', 1.0), 2)}")
        res_text = "👥 ALL REGISTERED USERS:\n\n" + ("\n".join(lines[:30]) if lines else "No registered users.")
        await query.edit_message_text(res_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_all_files" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        bots = get_bots()
        if not bots:
            await query.edit_message_text("📁 Hosted Files Directory:\n\nNo files hosted.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))
            return
        kb = []
        for bid, b in bots.items():
            kb.append([
                InlineKeyboardButton(f"📥 Get: {b['name']} (#{bid})", callback_data=f"adm_get_file_{bid}"),
                InlineKeyboardButton("📁 Dir", callback_data=f"adm_files_bot_{bid}")
            ])
        kb.append([InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")])
        lines = [f"📄 #{bid} - {b['name']} | Owner: @{b.get('owner_username')} ({b.get('owner_id')})" for bid, b in bots.items()]
        text = "📁 All Hosted Files Directory:\n\n" + "\n".join(lines)
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("adm_get_file_") and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        bot_id = data.split("_")[3]
        bots = get_bots()
        binfo = bots.get(bot_id)
        if not binfo or not os.path.exists(binfo["path"]):
            await query.answer("File not found.", show_alert=True)
            return
        with open(binfo["path"], "rb") as f:
            await context.bot.send_document(
                chat_id=user.id,
                document=f,
                filename=os.path.basename(binfo["path"]),
                caption=f"📄 Hosted File Archive\nBot ID: #{bot_id}"
            )
        await query.answer("File sent!", show_alert=True)

    elif data.startswith("adm_files_bot_") and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        bot_id = data.split("_")[3]
        bots = get_bots()
        binfo = bots.get(bot_id)
        if not binfo:
            await query.answer("Bot not found.", show_alert=True)
            return
        bot_dir = os.path.dirname(binfo["path"])
        files_list = os.listdir(bot_dir) if os.path.exists(bot_dir) else []
        f_str = "\n".join([f"📄 {f}" for f in files_list]) or "No extra files."
        kb = [
            [InlineKeyboardButton("📥 Download Main File", callback_data=f"adm_get_file_{bot_id}")],
            [InlineKeyboardButton("⬅️ Back to Files Directory", callback_data="adm_all_files")]
        ]
        await query.edit_message_text(f"📁 Bot #{bot_id} Workspace:\n{f_str}", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "adm_audit_logs" and is_admin(user.id):
        log_content = "No logs recorded."
        if os.path.exists(AUDIT_LOG_FILE):
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                log_content = f.read()[-3000:]
        await query.edit_message_text(f"📋 Admin Audit Logs (Actions & Changes):\n\n{log_content}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_db_query" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_db_query"] = True
        await query.edit_message_text("🔍 DB Query Handler\nType search keyword or user ID:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_cloud_backup" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        zip_path = os.path.join(BASE_DIR, "system_cloud_backup")
        archive_file = shutil.make_archive(zip_path, 'zip', HOSTED_DIR)
        with open(archive_file, 'rb') as f:
            await context.bot.send_document(
                chat_id=user.id,
                document=f,
                filename="ROLAX_SYSTEM_CLOUD_BACKUP.zip",
                caption="☁️ Full system cloud archive backup generated successfully."
            )
        if os.path.exists(archive_file):
            os.remove(archive_file)
        log_audit_action("Triggered 1-Click Cloud Backup", user.id)
        await query.answer("Full system backup dispatched!", show_alert=True)

    elif data == "adm_clean_cache" and is_admin(user.id):
        cleaned = 0
        for f in os.listdir(LOGS_DIR):
            fp = os.path.join(LOGS_DIR, f)
            if os.path.isfile(fp) and f.endswith(".log"):
                open(fp, 'w').close()
                cleaned += 1
        log_audit_action("Cleared System Cache & Log Files", user.id)
        await query.answer(f"🧹 Cleaned {cleaned} cache log files!", show_alert=True)

    elif data == "adm_live_logs" and is_admin(user.id):
        all_logs = ""
        for f in os.listdir(LOGS_DIR)[:5]:
            fp = os.path.join(LOGS_DIR, f)
            if os.path.isfile(fp):
                with open(fp, 'r', encoding='utf-8', errors='ignore') as lf:
                    all_logs += f"\n--- {f} ---\n" + "".join(lf.readlines()[-5:])
        await query.edit_message_text(f"📜 Live System Logs Viewer:\n\n{all_logs[-3500:] or 'No active logs.'}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_resource_limits" and is_admin(user.id):
        context.user_data["awaiting_res_limit"] = True
        cfg = get_config()
        await query.edit_message_text(
            f"⚡ RAM & CPU Limits Config\n\nCurrent Defaults:\nCPU Cores Limit: {cfg.get('default_cpu_limit', 8.0)}\nRAM Limit: {cfg.get('default_ram_limit', 8192)} MB\n\nTo update, send format: RAM_MB CPU_CORES:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_pending" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        pending = get_pending()
        if not pending:
            await query.edit_message_text("🔔 No pending approval requests.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))
            return
        for req_uid, path in list(pending.items()):
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{req_uid}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{req_uid}")]])
            await context.bot.send_message(user.id, f"🔔 Pending Request:\nUser ID: {req_uid}\nFile: {os.path.basename(path)}", reply_markup=kb)

    elif data == "adm_stats" and is_admin(user.id):
        bots = get_bots()
        txt = f"📊 SYSTEM METRICS STATS:\n\nRegistered Users: {len(get_users())}\nTotal Hosted Bots: {len(bots)}\nRunning Processes: {sum(1 for b in bots.values() if b.get('status') == 'RUNNING')}\nPending Approvals: {len(get_pending())}"
        await query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Admin Menu", callback_data="adm_back")]]))

    elif data == "adm_stop_all" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        for bid in list(get_bots().keys()):
            stop_bot_process(bid)
        log_audit_action("Stopped all running bot processes", user.id)
        await query.answer("All running bot instances terminated.", show_alert=True)

    elif data == "adm_restart_all" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        for bid in list(get_bots().keys()):
            start_bot_process(bid)
        log_audit_action("Restarted all registered processes", user.id)
        await query.answer("All bot instances restarted.", show_alert=True)

    elif data == "adm_ban" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_ban_id"] = True
        await query.edit_message_text("🚫 Ban User\nSend User ID to ban:")

    elif data == "adm_unban" and is_admin(user.id):
        if int(user.id) != int(ADMIN_ID):
            await query.answer("Restricted to Super Owner.", show_alert=True)
            return
        context.user_data["awaiting_unban_id"] = True
        await query.edit_message_text("✅ Unban User\nSend User ID to unban:")

    elif data == "adm_back" and is_admin(user.id):
        # Cancel any unfinished admin prompt when returning to the menu.
        for key in list(context.user_data):
            if key.startswith("awaiting_"):
                context.user_data.pop(key, None)
        users = get_users()
        bots = get_bots()
        config = get_config()
        vps_mem = psutil.virtual_memory()
        vps_cpu = psutil.cpu_percent(interval=None)
        role_title = "SUPER ADMIN" if int(user.id) == int(ADMIN_ID) else "SUB-ADMIN"

        text = (
            f"EXCLUSIVE ROLAX {role_title} CONTROL CENTER v3.18\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"Administrator: @{user.username or user.id} (ID: {user.id})\n"
            f"Registered Users: {len(users)}\n"
            f"Total Deployed Bots: {len(bots)}\n"
            f"Active Running Bots: {sum(1 for b in bots.values() if b.get('status') == 'RUNNING')}\n"
            f"Referral Reward Rate: {config.get('referral_reward', 0.25)} Credits\n"
            f"Core System Status: {config.get('bot_status', 'ON')}\n\n"
            f"Dedicated Server Metrics:\n"
            f"RAM Utilization: {round(vps_mem.used / (1024**3), 2)} GB / {round(vps_mem.total / (1024**3), 2)} GB ({vps_mem.percent}%)\n"
            f"CPU Load Average: {vps_cpu}%"
        )
        await query.edit_message_text(text, reply_markup=admin_panel_keyboard(user.id))

    elif data.startswith("approve_"):
        target_uid = data.split("_")[1]
        pending = get_pending()
        if target_uid in pending:
            file_path = pending[target_uid]
            filename = os.path.basename(file_path)
            bots = get_bots()
            new_id = str(len(bots) + 101)
            all_u = get_users()
            runtime = "javascript" if filename.endswith(".js") else "python"

            bots[new_id] = {
                "name": filename,
                "owner_id": int(target_uid),
                "owner_username": all_u.get(target_uid, {}).get("username", "N/A"),
                "status": "STOPPED",
                "path": file_path,
                "start_time": None,
                "deployed": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "runtime": runtime,
                "source": "upload",
                "autofix": True,
                "crash_count": 0
            }
            save_bots(bots)
            start_bot_process(new_id)
            del pending[target_uid]
            save_pending(pending)

            log_audit_action(f"Approved Bot #{new_id} for User {target_uid}", user.id)
            await query.edit_message_text(f"Approved & Deployed Bot #{new_id}")
            try:
                await context.bot.send_message(int(target_uid), f"Admin approved! Your application {filename} is now running 🟢")
            except Exception:
                pass

    elif data.startswith("reject_"):
        target_uid = data.split("_")[1]
        pending = get_pending()
        if target_uid in pending:
            del pending[target_uid]
            save_pending(pending)
            log_audit_action(f"Rejected Bot request for User {target_uid}", user.id)
            await query.edit_message_text("Request Rejected.")
            try:
                await context.bot.send_message(int(target_uid), "Admin declined your additional bot deployment request.")
            except Exception:
                pass

# ==================== INPUT HANDLERS ====================

async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    users = get_users()
    u_data = users.get(str(user.id), {})

    if u_data.get("banned", False) or u_data.get("restricted", False):
        await update.message.reply_text("Access Denied: Your account is restricted or banned.")
        return

    if is_admin(user.id) and context.user_data.pop("awaiting_db_restore", False):
        if int(user.id) != int(ADMIN_ID):
            await update.message.reply_text("Restricted to Super Owner.")
            return
        doc = update.message.document
        if not doc or not doc.file_name.endswith(".zip"):
            await update.message.reply_text("Please upload a valid .zip database backup file.")
            return

        zip_path = os.path.join(BASE_DIR, "restore_temp.zip")
        tfile = await context.bot.get_file(doc.file_id)
        await tfile.download_to_drive(zip_path)

        extract_dir = os.path.join(BASE_DIR, "extracted_restore")
        os.makedirs(extract_dir, exist_ok=True)
        shutil.unpack_archive(zip_path, extract_dir)

        for f in os.listdir(extract_dir):
            if f.endswith(".json"):
                shutil.move(os.path.join(extract_dir, f), BASE_DIR)

        shutil.rmtree(extract_dir, ignore_errors=True)
        if os.path.exists(zip_path):
            os.remove(zip_path)

        log_audit_action("Restored Database successfully via Bot Document Upload", user.id)
        await update.message.reply_text("Database Restored Successfully! All records have been updated from the backup.")
        return

    if is_admin(user.id) and context.user_data.pop("awaiting_media_broadcast", False):
        if int(user.id) != int(ADMIN_ID):
            await update.message.reply_text("Restricted to Super Owner.")
            return
        all_u = get_users()
        cnt = 0
        doc = update.message.document
        caption = update.message.caption or ""
        for uid in all_u:
            try:
                await context.bot.send_document(int(uid), document=doc.file_id, caption=caption)
                cnt += 1
            except Exception:
                pass
        log_audit_action(f"Sent Media Document Broadcast to {cnt} users", user.id)
        await update.message.reply_text(f"Media Broadcast sent to {cnt} users successfully!")
        return

    doc = update.message.document
    if not doc or not (doc.file_name.endswith(".py") or doc.file_name.endswith(".js")):
        await update.message.reply_text("Only .py and .js source files are supported.")
        return

    bots = get_bots()
    user_bot_count = sum(1 for b in bots.values() if b.get("owner_id") == user.id)
    max_allowed_bots = get_user_max_bots(user.id)

    user_dir = os.path.join(HOSTED_DIR, str(user.id))
    os.makedirs(user_dir, exist_ok=True)
    file_path = os.path.join(user_dir, doc.file_name)

    telegram_file = await context.bot.get_file(doc.file_id)
    await telegram_file.download_to_drive(file_path)

    if user_bot_count >= max_allowed_bots:
        pending = get_pending()
        pending[str(user.id)] = file_path
        save_pending(pending)

        await update.message.reply_text(
            f"Your bot limit ({max_allowed_bots}) has been reached (1 Credit = 1 Bot). Use a redeem code or refer friends to get more credits."
        )

        kb = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Approve", callback_data=f"approve_{user.id}"), InlineKeyboardButton("❌ Reject", callback_data=f"reject_{user.id}")]])
        try:
            await context.bot.send_message(
                ADMIN_ID,
                f"New Host Request (Credit Limit Reached)\nUser: @{user.username or 'N/A'} (ID: {user.id})\nFile: {doc.file_name}\nActive/Max: {user_bot_count}/{max_allowed_bots}",
                reply_markup=kb
            )
        except Exception:
            pass
    else:
        new_id = str(len(bots) + 101)
        runtime = "javascript" if doc.file_name.endswith(".js") else "python"

        bots[new_id] = {
            "name": doc.file_name,
            "owner_id": user.id,
            "owner_username": user.username or "N/A",
            "status": "STOPPED",
            "path": file_path,
            "start_time": None,
            "deployed": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "runtime": runtime,
            "source": "upload",
            "autofix": True,
            "crash_count": 0
        }
        save_bots(bots)
        log_session_action(user.id, user.username or "N/A", f"Uploaded and Deployed Bot #{new_id} ({doc.file_name})")

        if start_bot_process(new_id):
            await update.message.reply_text(f"Success! Your application {doc.file_name} is deployed and RUNNING 🟢 (Instance ID: #{new_id})")
        else:
            await update.message.reply_text(f"Saved file as ID #{new_id}, but process launch failed (Account might be restricted).")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if is_admin(user.id) and context.user_data.pop("awaiting_media_broadcast", False):
        if int(user.id) != int(ADMIN_ID):
            return
        all_u = get_users()
        cnt = 0
        photo = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        for uid in all_u:
            try:
                await context.bot.send_photo(int(uid), photo=photo, caption=caption)
                cnt += 1
            except Exception:
                pass
        log_audit_action(f"Sent Media Photo Broadcast to {cnt} users", user.id)
        await update.message.reply_text(f"Photo Broadcast sent to {cnt} users successfully!")

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    text = update.message.text.strip()

    if context.user_data.pop("expecting_redeem_code", False):
        codes = get_redeem_codes()
        users = get_users()
        uid = str(user.id)

        if text not in codes:
            await update.message.reply_text("Invalid or expired redeem code.")
            return

        cinfo = codes[text]
        if cinfo.get("used", False):
            await update.message.reply_text("This redeem code has already been used.")
            return

        redeemed_list = cinfo.get("redeemed_by_users", [])
        if uid in redeemed_list:
            await update.message.reply_text("You have already used this redeem code!")
            return

        max_limit = cinfo.get("max_uses", 1)
        if len(redeemed_list) >= max_limit:
            cinfo["used"] = True
            save_redeem_codes(codes)
            await update.message.reply_text("This redeem code has reached its maximum usage limit.")
            return

        if cinfo.get("expiry_time") and time.time() >= cinfo["expiry_time"]:
            cinfo["used"] = True
            save_redeem_codes(codes)
            await update.message.reply_text("This redeem code has expired.")
            return

        reward_credits = cinfo["credits"]
        users[uid]["credits"] = users[uid].get("credits", 1.0) + reward_credits
        
        redeemed_list.append(uid)
        cinfo["redeemed_by_users"] = redeemed_list
        if len(redeemed_list) >= max_limit:
            cinfo["used"] = True

        save_users(users)
        save_redeem_codes(codes)

        log_audit_action(f"User {user.id} redeemed code {text} for {reward_credits} credits", user.id)
        log_session_action(user.id, user.username or "N/A", f"Redeemed code {text}")
        await update.message.reply_text(f"Redeem Successful!\n\nAdded +{reward_credits} Credits to your wallet.")
        return

    if "editing_env_bot" in context.user_data:
        bot_id = context.user_data.pop("editing_env_bot")
        bots = get_bots()
        if bot_id in bots:
            env_path = os.path.join(os.path.dirname(bots[bot_id]["path"]), ".env")
            with open(env_path, "a", encoding="utf-8") as ef:
                ef.write(f"\n{text}")
            log_session_action(user.id, user.username or "N/A", f"Updated .env for Bot #{bot_id}")
            await update.message.reply_text("Environment variable appended to .env file successfully!")
            return

    if context.user_data.pop("expecting_github", False):
        if not text.startswith("http"):
            await update.message.reply_text("Invalid GitHub URL format.")
            return

        bots = get_bots()
        user_bot_count = sum(1 for b in bots.values() if b.get("owner_id") == user.id)
        max_allowed_bots = get_user_max_bots(user.id)
        if user_bot_count >= max_allowed_bots:
            await update.message.reply_text(f"Bot limit reached ({max_allowed_bots}). Redeem credits to unlock more slots.")
            return

        user_dir = os.path.join(HOSTED_DIR, str(user.id))
        os.makedirs(user_dir, exist_ok=True)
        repo_name = text.split("/")[-1].replace(".git", "")
        repo_dir = os.path.join(user_dir, repo_name)

        await update.message.reply_text("Cloning GitHub Repository...")
        proc = subprocess.run(["git", "clone", text, repo_dir], capture_output=True, text=True)

        if proc.returncode == 0:
            py_files = [f for f in os.listdir(repo_dir) if f.endswith(".py")]
            if py_files:
                entry_file = py_files[0]
                entry_path = os.path.join(repo_dir, entry_file)
                new_id = str(len(bots) + 101)

                bots[new_id] = {
                    "name": f"{repo_name}/{entry_file}",
                    "owner_id": user.id,
                    "owner_username": user.username or "N/A",
                    "status": "STOPPED",
                    "path": entry_path,
                    "start_time": None,
                    "deployed": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "runtime": "python",
                    "source": "github",
                    "autofix": True,
                    "crash_count": 0
                }
                save_bots(bots)
                start_bot_process(new_id)
                log_session_action(user.id, user.username or "N/A", f"Deployed GitHub repo as Bot #{new_id}")
                await update.message.reply_text(f"GitHub Repository Deployed Successfully as Instance #{new_id}!")
            else:
                await update.message.reply_text("Repository cloned, but no .py executable entrypoint was detected.")
        else:
            await update.message.reply_text(f"Git clone failed: {proc.stderr}")
        return

    if is_admin(user.id):
        if context.user_data.pop("awaiting_dm_user", False):
            if int(user.id) != int(ADMIN_ID):
                return
            try:
                parts = text.split(maxsplit=1)
                target_uid = int(parts[0])
                dm_msg = parts[1]
                await context.bot.send_message(chat_id=target_uid, text=f"Message from Admin:\n\n{dm_msg}")
                await update.message.reply_text(f"Message sent successfully to user {target_uid}!")
            except Exception as e:
                await update.message.reply_text(f"Failed to send DM. Error: {e}\nUse format: USER_ID MESSAGE")
            return

        if context.user_data.pop("awaiting_schedule_announcement", False):
            if int(user.id) != int(ADMIN_ID):
                return
            try:
                parts = text.split("|", 1)
                delay_mins = int(parts[0].strip())
                ann_msg = parts[1].strip()

                await update.message.reply_text(f"Announcement Scheduled!\nIt will be broadcasted to all users after {delay_mins} minutes.")
                
                async def delayed_broadcast():
                    await asyncio.sleep(delay_mins * 60)
                    all_u = get_users()
                    cnt = 0
                    for uid in all_u:
                        try:
                            await context.bot.send_message(int(uid), f"Scheduled Announcement:\n\n{ann_msg}")
                            cnt += 1
                        except Exception:
                            pass
                    log_audit_action(f"Executed Scheduled Announcement to {cnt} users: {ann_msg}", user.id)

                asyncio.create_task(delayed_broadcast())
            except Exception:
                await update.message.reply_text("Invalid syntax. Use format: DELAY_MINUTES | MESSAGE")
            return

        if context.user_data.pop("awaiting_add_credit", False):
            if int(user.id) != int(ADMIN_ID):
                return
            try:
                parts = text.split()
                target = parts[0]
                amount = float(parts[1])
                users = get_users()

                if target.lower() == "all":
                    for uid in users:
                        users[uid]["credits"] = users[uid].get("credits", 1.0) + amount
                    save_users(users)
                    log_audit_action(f"Added {amount} credits to ALL users", user.id)
                    await update.message.reply_text(f"Successfully added +{amount} Credits to ALL USERS!")
                else:
                    target_uid = str(int(target))
                    if target_uid in users:
                        users[target_uid]["credits"] = users[target_uid].get("credits", 1.0) + amount
                        save_users(users)
                        log_audit_action(f"Added {amount} credits to user {target_uid}", user.id)
                        await update.message.reply_text(f"Successfully added +{amount} Credits to User ID {target_uid}!")
                        try:
                            await context.bot.send_message(int(target_uid), f"Credit Updated!\nAdmin added +{amount} Credits to your wallet!")
                        except Exception:
                            pass
                    else:
                        await update.message.reply_text("User ID not found in database.")
            except Exception:
                await update.message.reply_text("Invalid syntax. Use format: USER_ID CREDITS or all CREDITS.")

        elif context.user_data.pop("awaiting_rem_credit", False):
            if int(user.id) != int(ADMIN_ID):
                return
            try:
                parts = text.split()
                target = parts[0]
                amount = float(parts[1])
                users = get_users()

                if target.lower() == "all":
                    for uid in users:
                        curr = users[uid].get("credits", 1.0)
                        users[uid]["credits"] = max(0.0, curr - amount)
                    save_users(users)
                    log_audit_action(f"Removed {amount} credits from ALL users", user.id)
                    await update.message.reply_text(f"Successfully removed {amount} Credits from ALL USERS!")
                else:
                    target_uid = str(int(target))
                    if target_uid in users:
                        curr = users[target_uid].get("credits", 1.0)
                        users[target_uid]["credits"] = max(0.0, curr - amount)
                        save_users(users)
                        log_audit_action(f"Removed {amount} credits from user {target_uid}", user.id)
                        await update.message.reply_text(f"Successfully removed {amount} Credits from User ID {target_uid}!")
                        try:
                            await context.bot.send_message(int(target_uid), f"Credit Updated!\nAdmin deducted {amount} Credits from your wallet.")
                        except Exception:
                            pass
                    else:
                        await update.message.reply_text("User ID not found in database.")
            except Exception:
                await update.message.reply_text("Invalid syntax. Use format: USER_ID CREDITS or all CREDITS.")

        elif context.user_data.pop("awaiting_ref_reward", False):
            if int(user.id) != int(ADMIN_ID):
                return
            try:
                val = float(text)
                cfg = get_config()
                cfg["referral_reward"] = val
                save_config(cfg)
                log_audit_action(f"Updated referral reward rate to {val}", user.id)
                await update.message.reply_text(f"Referral reward successfully updated to {val} Credits per invite!")
            except ValueError:
                await update.message.reply_text("Invalid number format.")

        elif context.user_data.pop("awaiting_redeem_create", False):
            if int(user.id) != int(ADMIN_ID):
                return
            try:
                parts = text.split()
                code_str = parts[0]
                cred_val = float(parts[1])
                duration_days = float(parts[2]) if len(parts) > 2 else 0
                max_users = int(parts[3]) if len(parts) > 3 else 1
                
                expiry_time = (time.time() + (duration_days * 86400)) if duration_days > 0 else None
                
                codes = get_redeem_codes()
                codes[code_str] = {
                    "credits": cred_val,
                    "used": False,
                    "max_uses": max_users,
                    "redeemed_by_users": [],
                    "expiry_time": expiry_time,
                    "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                save_redeem_codes(codes)
                log_audit_action(f"Created Redeem Code {code_str} for {cred_val} credits, duration {duration_days}d, max uses {max_users}", user.id)
                dur_text = f"{duration_days} Days" if duration_days > 0 else "Lifetime"
                await update.message.reply_text(f"Redeem Code Created Successfully!\n\n• Code: {code_str}\n• Value: {cred_val} Credits\n• Validity: {dur_text}\n• Max Users Limit: {max_users}")
            except Exception:
                await update.message.reply_text("Invalid syntax. Use format: CODE CREDITS DURATION_DAYS MAX_USERS")

        elif context.user_data.pop("awaiting_broadcast", False):
            if int(user.id) != int(ADMIN_ID):
                return
            all_u = get_users()
            cnt = 0
            for uid in all_u:
                try:
                    await context.bot.send_message(int(uid), text)
                    cnt += 1
                except Exception:
                    pass
            log_audit_action(f"Sent Broadcast to {cnt} users", user.id)
            await update.message.reply_text(f"Global Text Broadcast delivered to {cnt} users.")

        elif context.user_data.pop("awaiting_ban_id", False):
            if int(user.id) != int(ADMIN_ID):
                return
            all_u = get_users()
            if text in all_u:
                all_u[text]["banned"] = True
                save_users(all_u)
                log_audit_action(f"Banned User {text}", user.id)
                await update.message.reply_text(f"User ID {text} has been BANNED.")
            else:
                await update.message.reply_text("User ID not found.")

        elif context.user_data.pop("awaiting_unban_id", False):
            if int(user.id) != int(ADMIN_ID):
                return
            all_u = get_users()
            if text in all_u:
                all_u[text]["banned"] = False
                save_users(all_u)
                log_audit_action(f"Unbanned User {text}", user.id)
                await update.message.reply_text(f"User ID {text} has been UNBANNED.")
            else:
                await update.message.reply_text("User ID not found.")

        elif context.user_data.pop("awaiting_restrict_id", False):
            if int(user.id) != int(ADMIN_ID):
                return
            all_u = get_users()
            if text in all_u:
                all_u[text]["restricted"] = True
                save_users(all_u)
                bots = get_bots()
                for bid, binfo in list(bots.items()):
                    if str(binfo.get("owner_id")) == text:
                        stop_bot_process(bid)
                log_audit_action(f"Restricted User {text} and stopped their bots", user.id)
                await update.message.reply_text(f"User ID {text} is now RESTRICTED 🔒. All their bots have been stopped and hosting is disabled.")
                try:
                    await context.bot.send_message(int(text), "⚠️ Your hosting account has been restricted by the admin.")
                except Exception:
                    pass
            else:
                await update.message.reply_text("User ID not found.")

        elif context.user_data.pop("awaiting_unrestrict_id", False):
            if int(user.id) != int(ADMIN_ID):
                return
            all_u = get_users()
            if text in all_u:
                all_u[text]["restricted"] = False
                save_users(all_u)
                log_audit_action(f"Unrestricted User {text}", user.id)
                await update.message.reply_text(f"User ID {text} restrictions have been lifted successfully 🔓.")
                try:
                    await context.bot.send_message(int(text), "🎉 Your hosting account restrictions have been lifted by the admin!")
                except Exception:
                    pass
            else:
                await update.message.reply_text("User ID not found.")

        elif context.user_data.pop("awaiting_stop_bot_id", False):
            if int(user.id) != int(ADMIN_ID):
                return
            bots = get_bots()
            if text in bots:
                stop_bot_process(text)
                log_audit_action(f"Admin forcibly stopped Bot ID #{text}", user.id)
                await update.message.reply_text(f"Bot ID #{text} has been successfully stopped!")
            else:
                await update.message.reply_text("Bot ID not found.")

        elif context.user_data.pop("awaiting_del_bot_id", False):
            if int(user.id) != int(ADMIN_ID):
                return
            bots = get_bots()
            if text in bots:
                binfo = bots[text]
                stop_bot_process(text)
                if os.path.exists(binfo["path"]):
                    try:
                        os.remove(binfo["path"])
                    except Exception:
                        pass
                del bots[text]
                save_bots(bots)
                log_audit_action(f"Admin deleted Bot ID #{text} and its files", user.id)
                await update.message.reply_text(f"Bot ID #{text} and its source files have been permanently deleted.")
            else:
                await update.message.reply_text("Bot ID not found.")

        elif context.user_data.pop("awaiting_view_user", False):
            if int(user.id) != int(ADMIN_ID):
                return
            all_u = get_users()
            bots = get_bots()
            if text in all_u:
                uinfo = all_u[text]
                ubots = [bid for bid, b in bots.items() if b.get("owner_id") == int(text)]
                await update.message.reply_text(
                    f"User Profile Matrix\n"
                    f"ID: {text}\n"
                    f"Name: {uinfo.get('name')}\n"
                    f"Username: @{uinfo.get('username')}\n"
                    f"Premium: {uinfo.get('premium', False)}\n"
                    f"Restricted: {uinfo.get('restricted', False)}\n"
                    f"Credits: {round(uinfo.get('credits', 1.0), 2)}\n"
                    f"Joined: {uinfo.get('joined')}\n"
                    f"Banned: {uinfo.get('banned')}\n"
                    f"Active Bot IDs: {ubots}"
                )
            else:
                await update.message.reply_text("User ID not found in database.")

        elif context.user_data.pop("awaiting_give_prem", False):
            try:
                parts = text.split()
                target_uid = str(int(parts[0]))
                days = int(parts[1])
                users = get_users()
                
                if target_uid in users:
                    expiry_timestamp = time.time() + (days * 86400)
                    users[target_uid]["premium"] = True
                    users[target_uid]["premium_expiry"] = expiry_timestamp
                    save_users(users)
                    
                    log_audit_action(f"Granted Premium VIP via panel to User {target_uid} for {days} days", user.id)
                    await update.message.reply_text(f"User {target_uid} successfully upgraded to Premium VIP for {days} Days!")
                    try:
                        await context.bot.send_message(int(target_uid), f"Congratulations!\nYou have been granted Premium VIP status for {days} Days by the admin!")
                    except Exception:
                        pass
                else:
                    await update.message.reply_text("User ID not found.")
            except Exception:
                await update.message.reply_text("Invalid syntax. Use format: USER_ID DAYS")

        elif context.user_data.pop("awaiting_rem_prem", False):
            if int(user.id) != int(ADMIN_ID):
                return
            try:
                target_uid = str(int(text))
                users = get_users()
                if target_uid in users:
                    users[target_uid]["premium"] = False
                    users[target_uid]["premium_expiry"] = None
                    save_users(users)
                    log_audit_action(f"Removed Premium status via panel from User {target_uid}", user.id)
                    await update.message.reply_text(f"User {target_uid} has been downgraded to Free Member.")
                    try:
                        await context.bot.send_message(int(target_uid), "Your Premium VIP status has been removed by the admin.")
                    except Exception:
                        pass
                else:
                    await update.message.reply_text("User ID not found.")
            except ValueError:
                await update.message.reply_text("Invalid User ID format.")

        elif context.user_data.pop("awaiting_fj_add", False):
            if int(user.id) != int(ADMIN_ID):
                return
            channels = get_force_join()
            if text not in channels:
                channels.append(text)
                save_force_join(channels)
                log_audit_action(f"Added Force Join channel: {text}", user.id)
                await update.message.reply_text(f"Channel {text} added to Force Join successfully!")
            else:
                await update.message.reply_text("Channel already exists in list.")

        elif context.user_data.pop("awaiting_fj_rem", False):
            if int(user.id) != int(ADMIN_ID):
                return
            channels = get_force_join()
            if text in channels:
                channels.remove(text)
                save_force_join(channels)
                log_audit_action(f"Removed Force Join channel: {text}", user.id)
                await update.message.reply_text(f"Channel {text} removed from Force Join!")
            else:
                await update.message.reply_text("Channel not found in list.")

        elif context.user_data.pop("awaiting_add_admin", False):
            if int(user.id) != int(ADMIN_ID):
                return
            try:
                new_admin_id = int(text)
                admins = get_admins()
                if new_admin_id not in admins:
                    admins.append(new_admin_id)
                    save_admins(admins)
                    log_audit_action(f"Added Sub-Admin: {new_admin_id}", user.id)
                    await update.message.reply_text(f"User {new_admin_id} added as Sub-Admin!")
                    try:
                        await context.bot.send_message(new_admin_id, "Congratulations!\nYou have been promoted to Sub-Admin by the owner. Send /admin to open your panel.")
                    except Exception:
                        pass
                else:
                    await update.message.reply_text("User is already an admin.")
            except ValueError:
                await update.message.reply_text("Invalid Chat ID.")

        elif context.user_data.pop("awaiting_remove_admin", False):
            if int(user.id) != int(ADMIN_ID):
                return
            try:
                rem_admin_id = int(text)
                if rem_admin_id == ADMIN_ID:
                    await update.message.reply_text("Cannot remove primary super owner!")
                    return
                admins = get_admins()
                if rem_admin_id in admins:
                    admins.remove(rem_admin_id)
                    save_admins(admins)
                    log_audit_action(f"Removed Admin: {rem_admin_id}", user.id)
                    await update.message.reply_text(f"Admin {rem_admin_id} removed successfully!")
                else:
                    await update.message.reply_text("Admin ID not found.")
            except ValueError:
                await update.message.reply_text("Invalid ID format.")

        elif context.user_data.pop("awaiting_db_query", False):
            if int(user.id) != int(ADMIN_ID):
                return
            bots = get_bots()
            users = get_users()
            res = [f"Found in Users: {uid}" for uid in users if text in uid or text in users[uid].get("username", "")]
            res += [f"Found in Bots: #{bid} ({b['name']})" for bid, b in bots.items() if text in bid or text in b['name']]
            await update.message.reply_text("Database Query Results:\n\n" + ("\n".join(res) if res else "No matches found."))

        elif context.user_data.pop("awaiting_res_limit", False):
            try:
                ram, cpu = text.split()
                cfg = get_config()
                cfg["default_ram_limit"] = int(ram)
                cfg["default_cpu_limit"] = float(cpu)
                save_config(cfg)
                log_audit_action(f"Updated Hardware Defaults: RAM {ram}MB, CPU {cpu}", user.id)
                await update.message.reply_text(f"Hardware Limits Updated!\nRAM Cap: {ram} MB\nCPU Cores: {cpu}")
            except Exception:
                await update.message.reply_text("Invalid syntax. Use: 8192 8.0")

# ==================== MAIN APPLICATION ====================

async def post_init(app: Application) -> None:
    asyncio.create_task(auto_fix_guardian_task(app))
    asyncio.create_task(background_expiry_guardian(app))
    asyncio.create_task(daily_reminder_guardian(app))

def main() -> None:
    req_path = os.path.join(BASE_DIR, "requirements.txt")
    if not os.path.exists(req_path):
        with open(req_path, "w", encoding="utf-8") as rf:
            rf.write("python-telegram-bot\npsutil\n")

    get_users()
    get_bots()
    get_pending()
    get_config()
    get_admins()
    get_force_join()
    get_redeem_codes()

    bots = get_bots()
    for bid, binfo in bots.items():
        if binfo.get("status") == "RUNNING":
            start_bot_process(bid)

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler(["redeem", "Redeem", "REDEEM"], redeem_command))
    app.add_handler(CommandHandler(["admin", "Admin", "ADMIN"], admin_command))
    app.add_handler(CommandHandler("addadmin", add_admin_command))
    app.add_handler(CommandHandler("addpremium", add_premium_command))

    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_document))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("EXCLUSIVE ROLAX HOSTING V2 Active with Direct Stop/Delete Bot Controls!")
    app.run_polling()

if __name__ == "__main__":
    main()
