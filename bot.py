import logging
import os
import requests
import re
import json
import asyncio
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# ====== CONFIG ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_TG_ID = os.getenv("OWNER_ID") 
OWNER_NAME = "Mudasir"
BRAND = "🔥 𝗣𝗢𝗪𝗘𝗥𝗘𝗗 𝗕𝗬 𝗠𝗨𝗗𝗔𝗦𝗜𝗥 𝗧𝗘𝗖𝗛 🔥"

# CREDENTIALS
ADMIN_USER = "7944"
ADMIN_PASS = "10-16-2025@Swi"

# URLS
BASE_URL = "http://mysmsportal.com"
URLS = {
    "login": "/index.php?login=1",
    "home": "/index.php?opt=shw_all_v2",
    "allo": "/index.php?opt=shw_allo",
    "stats": "/index.php?opt=shw_sts_today_sum",
    "reclaim": "/index.php?opt=rec_bulk_v2",
    "manage": "/index.php?opt=shw_mge"
}

# HEADERS
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": BASE_URL,
    "Referer": BASE_URL + "/index.php?login=1",
}

# MEMORY (RAM Based)
ACTIVE_SESSIONS = {} # {uid: session_object}
USER_CREDS = {} # {uid: {'user':, 'pass':, 'name':, 'role':}}

# STATES
(CREATE_NAME, CREATE_PASS, 
 ADMIN_SET_ID, ADMIN_SET_PASS,
 REC_CLIENT, REC_RANGE, REC_CONFIRM,
 NUM_RANGE, NUM_TYPE, NUM_FORMAT) = range(10)

# LOGGING
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# ====== 🛠️ SESSION ENGINE ======

def get_user_session(uid):
    uid = str(uid)
    
    # 1. Check if we have creds
    if uid not in USER_CREDS: return None
    creds = USER_CREDS[uid]
    
    # 2. Check if we have active session
    if uid in ACTIVE_SESSIONS:
        s = ACTIVE_SESSIONS[uid]
        # Verify if alive
        try:
            r = s.get(BASE_URL + URLS['home'], allow_redirects=False, timeout=5)
            if r.status_code == 200 and "login" not in r.url:
                return s # Alive
        except: pass
    
    # 3. Create New Login
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        r = s.post(BASE_URL + URLS['login'], data={"user": creds['user'], "password": creds['pass']}, timeout=15)
        if "opt=shw_all" in r.url or "log out" in r.text.lower():
            ACTIVE_SESSIONS[uid] = s # Save session with cookie
            return s
    except Exception as e:
        logger.error(f"Login Error: {e}")
        
    return None

# ====== 🌐 API WRAPPERS ======

def api_create_client(s, name, password):
    try:
        s.get(BASE_URL + URLS['manage'], timeout=10)
        d = {"subnme": name, "passwd1": password, "passwd2": password, "newcli": "1"}
        r = s.post(BASE_URL + URLS['manage'], data=d, timeout=20)
        return name in r.text
    except: return False

def api_get_clients(s):
    try:
        r = s.get(BASE_URL + URLS['manage'], timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        clients = []
        for tr in soup.select("table tr"):
            tds = tr.find_all("td")
            if len(tds) > 3:
                row = " | ".join([t.get_text(strip=True) for t in tds])
                if "User" not in row and len(row) > 5: clients.append(row)
        return clients
    except: return []

def api_get_stats(s):
    try:
        r = s.get(BASE_URL + URLS['stats'], timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        stats = []
        # Try table
        for tr in soup.select("table tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                stats.append(f"🔹 {tds[0].get_text(strip=True)}: {tds[1].get_text(strip=True)}")
        # Try text
        if not stats:
            text = soup.get_text()
            for line in text.splitlines():
                if any(x in line for x in ["Total", "Sent", "Delivered"]):
                    stats.append(f"🔸 {line.strip()}")
        return "\n".join(stats) if stats else "⚠️ No Data."
    except: return "Error."

def api_get_ranges(s, page_key, sel_name):
    try:
        # GET first
        r = s.get(BASE_URL + URLS[page_key], timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        return [{"text": o.get_text(" ", strip=True), "value": o.get("value")} for o in soup.select(f"select[name={sel_name}] option") if o.get("value")]
    except: return []

def api_post_ranges(s, cid):
    try:
        r = s.post(BASE_URL + URLS['reclaim'], data={"idd": cid}, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        return [{"text": o.get_text(" ", strip=True), "value": o.get("value")} for o in soup.select("select[name=range] option") if o.get("value")]
    except: return []

def api_fetch_numbers(s, rng, typ):
    try:
        s.post(BASE_URL + URLS['allo'], data={"cdecode1": rng, "selected1": "1", "cdecode": ""}, timeout=10)
        r = s.post(BASE_URL + URLS['allo'], data={"type": typ, "selected1": "1", "selected2": "1", "cdecode": "", "cdecode1": rng}, timeout=25)
        text = BeautifulSoup(r.text, "lxml").get_text(separator="\n")
        return list(set(re.findall(r'\b\d{7,16}\b', text)))
    except: return []

def api_reclaim(s, cid, rng):
    try:
        r = s.post(BASE_URL + URLS['reclaim'], data={"idd": cid, "range": rng, "reclaim": "YES"}, timeout=15)
        return r.status_code == 200
    except: return False

# ====== 🤖 HANDLERS ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("⚡ <b>Connecting...</b>", parse_mode="HTML")
    uid = str(update.effective_user.id)
    
    # Auto Owner
    if OWNER_TG_ID and uid == str(OWNER_TG_ID):
        USER_CREDS[uid] = {'user': ADMIN_USER, 'pass': ADMIN_PASS, 'name': OWNER_NAME, 'role': 'admin'}
    
    if uid in USER_CREDS:
        c = USER_CREDS[uid]
        await show_dashboard(msg, c['name'], c['user'], c['role'])
    else:
        txt = (
            f"💫 <b>ASSALAM-O-ALAIKUM {update.effective_user.first_name}!</b> 💫\n\n"
            f"🌹 <i>\"Dunya Ki Bheed Me Hum Tanha Reh Gaye...\"</i> 🌹\n\n"
            f"👑 <b>{OWNER_NAME}'s PRIVATE SERVER</b>\n"
            f"🔒 <b>Status:</b> <code>LOCKED</code>\n\n"
            f"👇 <i>Request Access:</i>"
        )
        kb = [[InlineKeyboardButton("💖 SEND REQUEST", callback_data="req_login")]]
        await msg.edit_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def show_dashboard(message, name, pid, role):
    rank = f"👑 {OWNER_NAME}" if role == 'admin' else "👤 𝐂𝐥𝐢𝐞𝐧𝐭"
    txt = (
        f"🔥 <b>MUDASIR VIP PANEL</b> 🔥\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Name:</b> {name}\n"
        f"🆔 <b>ID:</b> <code>{pid}</code>\n"
        f"🔰 <b>Rank:</b> {rank}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <i>Select Action:</i>"
    )
    kb = []
    if role == 'admin':
        kb.append([InlineKeyboardButton("👤 Create Client", callback_data="new_cli"), InlineKeyboardButton("♻️ Reclaim", callback_data="rec_start")])
        kb.append([InlineKeyboardButton("📋 View Clients", callback_data="view_cli")])
    
    kb.append([
        InlineKeyboardButton("🔢 Get Numbers", callback_data="get_num"),
        InlineKeyboardButton("📊 Stats", callback_data="view_stats")
    ])
    kb.append([InlineKeyboardButton("🔌 Logout", callback_data="logout")])
    
    # Edit if callback, else edit message passed
    try: await message.edit_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    except: pass

async def menu_cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid in USER_CREDS:
        c = USER_CREDS[uid]
        await show_dashboard(update.callback_query.message, c['name'], c['user'], c['role'])
    else:
        await update.callback_query.message.edit_text("Expired. /start")

# --- LOGIN REQUEST ---
async def request_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not OWNER_TG_ID: return
    context.bot_data[f"req_{uid}"] = update.effective_chat.id
    
    txt = f"🚨 <b>NEW USER:</b> {update.effective_user.first_name} (`{uid}`)"
    kb = [[InlineKeyboardButton("✅ Accept", callback_data=f"ok_{uid}"), InlineKeyboardButton("❌ Reject", callback_data=f"no_{uid}")]]
    try: await context.bot.send_message(chat_id=OWNER_TG_ID, text=txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    except: pass
    await query.edit_message_text("✅ <b>Request Sent!</b> Wait for approval.")

async def admin_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    target = data.split("_")[1]
    if "no_" in data:
        await query.edit_message_text("❌ Rejected.")
        return ConversationHandler.END
    context.user_data['target_uid'] = target
    await query.edit_message_text("✍️ <b>Enter Portal User ID:</b>", parse_mode="HTML")
    return ADMIN_SET_ID

async def set_pid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_pid'] = update.message.text.strip()
    await update.message.reply_text("🔑 <b>Enter Password:</b>", parse_mode="HTML")
    return ADMIN_SET_PASS

async def set_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pw = update.message.text.strip()
    pid = context.user_data['new_pid']
    tid = context.user_data['target_uid']
    
    # Save creds temporarily to verify
    s = requests.Session()
    s.headers.update(HEADERS)
    try:
        r = s.post(BASE_URL + URLS['login'], data={"user": pid, "password": pw}, timeout=15)
        if "opt=shw_all" in r.url or "log out" in r.text.lower():
            USER_CREDS[str(tid)] = {'user': pid, 'pass': pw, 'name': f"User {pid}", 'role': 'client'}
            await update.message.reply_text("✅ <b>Approved!</b>", parse_mode="HTML")
            
            # Notify User
            origin = context.bot_data.get(f"req_{tid}", tid)
            welcome = f"🎉 <b>APPROVED!</b>\n🆔 <code>{pid}</code>\n🔑 <code>{pw}</code>\n\nType /start"
            try: await context.bot.send_message(chat_id=origin, text=welcome, parse_mode="HTML")
            except: pass
        else:
            await update.message.reply_text("❌ <b>Invalid Creds.</b>", parse_mode="HTML")
    except:
        await update.message.reply_text("❌ <b>Connection Error.</b>", parse_mode="HTML")
    return ConversationHandler.END

# --- CREATE CLIENT ---
async def create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🆕 <b>Enter Name:</b>", parse_mode="HTML")
    return CREATE_NAME

async def create_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['cname'] = update.message.text.strip()
    await update.message.reply_text("🔑 <b>Password:</b>", parse_mode="HTML")
    return CREATE_PASS

async def create_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['cpass'] = update.message.text.strip()
    await update.message.reply_text("🔐 <b>Confirm Password:</b>", parse_mode="HTML")
    return CREATE_CONFIRM

async def create_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    conf = update.message.text.strip()
    orig = context.user_data['cpass']
    nm = context.user_data['cname']
    
    if conf != orig:
        await update.message.reply_text("❌ Mismatch. /start again.")
        return ConversationHandler.END
        
    msg = await update.message.reply_text("⚙️ <b>Creating...</b>", parse_mode="HTML")
    s = get_user_session(update.effective_user.id)
    
    if s and api_create_client(s, nm, orig):
        await msg.edit_text(f"✅ <b>Client Created!</b>\n\nName: {nm}\nPass: <code>{orig}</code>", parse_mode="HTML")
    else:
        await msg.edit_text("❌ <b>Failed.</b>", parse_mode="HTML")
    return ConversationHandler.END

# --- GET NUMBERS ---
async def num_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    
    await query.edit_message_text("⏳ <b>Fetching...</b>", parse_mode="HTML")
    s = get_user_session(uid)
    if not s:
        await query.edit_message_text("❌ Error. /start", parse_mode="HTML")
        return ConversationHandler.END
        
    ranges = api_get_ranges(s, 'allo', 'cdecode1')
    if not ranges:
        await query.edit_message_text("❌ No Ranges.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
        return ConversationHandler.END
        
    context.user_data['n_ranges'] = ranges
    btns = [InlineKeyboardButton(r['text'], callback_data=f"n_{i}") for i, r in enumerate(ranges[:20])]
    chunks = [btns[i:i+1] for i in range(0, len(btns), 1)]
    chunks.append([InlineKeyboardButton("🔙 Cancel", callback_data="main_menu")])
    await query.edit_message_text("👇 <b>Select Country:</b>", reply_markup=InlineKeyboardMarkup(chunks), parse_mode="HTML")
    return NUM_RANGE

async def num_rng_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("_")[1])
    context.user_data['n_rng'] = context.user_data['n_ranges'][idx]
    kb = [[InlineKeyboardButton("🔴 Not Active", callback_data="t_N")], [InlineKeyboardButton("🟢 Active", callback_data="t_A")]]
    await query.edit_message_text(f"🌍 <b>Selected:</b> {context.user_data['n_rng']['text']}\n👇 <b>Type:</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    return NUM_TYPE

async def num_type_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    t = query.data.split("_")[1]
    await query.edit_message_text("🔎 <b>Scanning...</b>", parse_mode="HTML")
    
    s = get_user_session(update.effective_user.id)
    rng = context.user_data['n_rng']['value']
    nums = api_fetch_numbers(s, rng, t)
    
    if not nums:
        await query.edit_message_text("❌ <b>No Numbers.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
        return ConversationHandler.END
    
    context.user_data['n_res'] = nums
    sample = nums[0]
    detected = sample[:3]
    for c in ["380", "994", "62", "84", "92", "91", "44", "7"]:
        if sample.startswith(c) or sample.startswith("+"+c):
            detected = c; break
            
    kb = [[InlineKeyboardButton(f"With Code (+{detected}..)", callback_data="f_full")], [InlineKeyboardButton(f"Without Code", callback_data="f_cut")]]
    await query.edit_message_text(f"✅ <b>Found {len(nums)}!</b>\n📋 <b>Format?</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    return NUM_FORMAT

async def num_fmt_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    fmt = query.data
    raw = context.user_data['n_res']
    await query.edit_message_text("🚀 <b>Sending...</b>", parse_mode="HTML")
    
    final = []
    codes = ["380", "994", "62", "84", "92", "91", "1", "7", "44"]
    for n in raw:
        clean = n.replace("+", "")
        if fmt == "f_cut":
            cut = False
            for c in codes:
                if clean.startswith(c):
                    final.append(clean[len(c):])
                    cut = True; break
            if not cut: final.append(clean)
        else: final.append(f"+{clean}")
            
    chunks = [final[i:i+50] for i in range(0, len(final), 50)]
    for c in chunks:
        msg = "\n".join([f"<code>{n}</code>" for n in c])
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode="HTML")
        await asyncio.sleep(0.3)
    
    with open("nums.txt", "w") as f: f.write("\n".join(final))
    await context.bot.send_document(chat_id=update.effective_chat.id, document=open("nums.txt", "rb"), caption=f"📂 <b>List</b>\n{BRAND}", parse_mode="HTML")
    os.remove("nums.txt")
    await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ <b>Done.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
    return ConversationHandler.END

# --- RECLAIM ---
async def rec_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    if uid != OWNER_TG_ID: return
    await query.edit_message_text("♻️ <b>Fetching...</b>", parse_mode="HTML")
    
    s = get_user_session(uid)
    clients = api_get_ranges(s, 'reclaim', 'idd') # Reusing ranges function for client list
    
    if not clients:
        await query.edit_message_text("❌ No Clients.", parse_mode="HTML")
        return ConversationHandler.END
        
    context.user_data['rec_clients'] = clients
    btns = [InlineKeyboardButton(c['text'], callback_data=f"rc_{i}") for i, c in enumerate(clients[:30])]
    chunks = [btns[i:i+2] for i in range(0, len(btns), 2)]
    chunks.append([InlineKeyboardButton("🔙 Cancel", callback_data="main_menu")])
    await query.edit_message_text("👇 <b>Select Client:</b>", reply_markup=InlineKeyboardMarkup(chunks), parse_mode="HTML")
    return REC_CLIENT

async def rec_cli_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("_")[1])
    cname = context.user_data['rec_clients'][idx]['text']
    cid = context.user_data['rec_clients'][idx]['value']
    context.user_data['rec_cid'] = cid
    
    await query.edit_message_text(f"♻️ <b>Client:</b> {cname}\n⏳ <b>Ranges...</b>", parse_mode="HTML")
    s = get_user_session(update.effective_user.id)
    ranges = api_post_ranges(s, cid)
    
    if not ranges:
        await query.edit_message_text("❌ No Ranges.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
        return ConversationHandler.END
    context.user_data['rec_rngs'] = ranges
    btns = [InlineKeyboardButton(r['text'], callback_data=f"rr_{i}") for i, r in enumerate(ranges)]
    chunks = [btns[i:i+1] for i in range(0, len(btns), 1)]
    chunks.append([InlineKeyboardButton("🔙 Cancel", callback_data="main_menu")])
    await query.edit_message_text("👇 <b>Select Range:</b>", reply_markup=InlineKeyboardMarkup(chunks), parse_mode="HTML")
    return REC_RANGE

async def rec_rng_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("_")[1])
    rname = context.user_data['rec_rngs'][idx]['text']
    context.user_data['rec_rval'] = context.user_data['rec_rngs'][idx]['value']
    
    kb = [[InlineKeyboardButton("✅ RECLAIM", callback_data="do_rec"), InlineKeyboardButton("❌ CANCEL", callback_data="main_menu")]]
    await query.edit_message_text(f"⚠️ <b>CONFIRM?</b>\nRange: {rname}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    return REC_CONFIRM

async def rec_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "main_menu":
        await menu_cb(update, context)
        return ConversationHandler.END
    
    await query.edit_message_text("⚙️ <b>Processing...</b>", parse_mode="HTML")
    s = get_user_session(update.effective_user.id)
    if api_reclaim(s, context.user_data['rec_cid'], context.user_data['rec_rval']):
        await query.edit_message_text("✅ <b>SUCCESS!</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
    else:
        await query.edit_message_text("❌ <b>Failed.</b>", parse_mode="HTML")
    return ConversationHandler.END

# --- EXTRAS ---
async def view_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    await query.edit_message_text("⏳ <b>Fetching...</b>", parse_mode="HTML")
    s = get_user_session(uid)
    txt = api_get_stats(s)
    await query.edit_message_text(f"📊 <b>STATS</b>\n━━━━━━━━\n{txt}\n━━━━━━━━", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")

async def view_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ <b>Loading...</b>", parse_mode="HTML")
    s = get_user_session(update.effective_user.id)
    clients = api_get_clients(s)
    
    if not clients:
        await query.edit_message_text("⚠️ None Found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
        return
        
    with open("clients.txt", "w") as f: f.write("\n".join(clients))
    await context.bot.send_document(chat_id=update.effective_chat.id, document=open("clients.txt", "rb"), caption="📋 Clients")
    os.remove("clients.txt")
    await menu_cb(update, context)

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid in USER_CREDS: del USER_CREDS[uid]
    if uid in ACTIVE_SESSIONS: del ACTIVE_SESSIONS[uid]
    await update.callback_query.edit_message_text("🔒 <b>Logged Out.</b>", parse_mode="HTML")
    return ConversationHandler.END

def main():
    if not BOT_TOKEN: return
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    
    # Handlers
    app.add_handler(CallbackQueryHandler(request_login, pattern="req_login"))
    app.add_handler(CallbackQueryHandler(view_clients, pattern="view_cli"))
    app.add_handler(CallbackQueryHandler(view_stats, pattern="view_stats"))
    app.add_handler(CallbackQueryHandler(logout, pattern="logout"))
    app.add_handler(CallbackQueryHandler(menu_cb, pattern="main_menu"))

    # CONVERSATIONS
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(admin_verify, pattern="^(ok_|no_)")],
        states={ADMIN_SET_ID: [MessageHandler(filters.TEXT, set_pid)], ADMIN_SET_PASS: [MessageHandler(filters.TEXT, set_pass)]},
        fallbacks=[CommandHandler("start", start)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(create_start, pattern="new_cli")],
        states={
            CREATE_NAME: [MessageHandler(filters.TEXT, create_name)], 
            CREATE_PASS: [MessageHandler(filters.TEXT, create_pass)],
            CREATE_CONFIRM: [MessageHandler(filters.TEXT, create_confirm)]
        },
        fallbacks=[CommandHandler("start", start)]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(num_start, pattern="get_num")],
        states={
            NUM_RANGE: [CallbackQueryHandler(num_rng_sel, pattern="^n_")],
            NUM_TYPE: [CallbackQueryHandler(num_type_sel, pattern="^t_")],
            NUM_FORMAT: [CallbackQueryHandler(num_fmt_sel, pattern="^f_")]
        },
        fallbacks=[CallbackQueryHandler(menu_cb, pattern="main_menu")]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(rec_start, pattern="rec_start")],
        states={
            REC_CLIENT: [CallbackQueryHandler(rec_cli_sel, pattern="^rc_")],
            REC_RANGE: [CallbackQueryHandler(rec_rng_sel, pattern="^rr_")],
            REC_CONFIRM: [CallbackQueryHandler(rec_do, pattern="^(do_rec|main_menu)")]
        },
        fallbacks=[CallbackQueryHandler(menu_cb, pattern="main_menu")]
    ))

    print("BOT STARTED...")
    app.run_polling()

if __name__ == "__main__":
    main()
