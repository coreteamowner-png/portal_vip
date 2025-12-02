import logging
import os
import requests
import re
import json
import asyncio
import time
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# ====== ⚙️ CONFIGURATION ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_TG_ID = os.getenv("OWNER_ID") 
OWNER_NAME = "Mudasir"
BRAND = "🔥 𝗣𝗢𝗪𝗘𝗥𝗘𝗗 𝗕𝗬 𝗠𝗨𝗗𝗔𝗦𝗜𝗥 𝗧𝗘𝗖𝗛 🔥"

# 👑 DEFAULT PORTAL CREDENTIALS
ADMIN_USER = "7944"
ADMIN_PASS = "10-16-2025@Swi"

# 🌐 URLS
BASE_URL = "http://mysmsportal.com"
URLS = {
    "login": "/index.php?login=1",
    "home": "/index.php?opt=shw_all_v2",
    "allo": "/index.php?opt=shw_allo",
    "stats": "/index.php?opt=shw_sts_today_sum",
    "reclaim": "/index.php?opt=rec_bulk_v2",
    "manage": "/index.php?opt=shw_mge"
}

# 📱 HEADERS
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": BASE_URL,
    "Referer": BASE_URL + "/index.php?login=1",
}

# 💾 MEMORY
ACTIVE_SESSIONS = {} # {uid: session_obj}
USER_DB = {} # {uid: {'user':, 'pass':, 'name':}}

# 🚦 STATES
(CREATE_NAME, CREATE_PASS, CREATE_CONFIRM,
 ADMIN_SET_ID, ADMIN_SET_PASS,
 REC_CLIENT, REC_RANGE, REC_CONFIRM,
 NUM_RANGE, NUM_TYPE, NUM_FORMAT) = range(10)

# 📝 LOGGING
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# ====== 🛠️ SESSION ENGINE ======

def get_session(uid):
    uid = str(uid)
    # Check DB
    if uid not in USER_DB: return None
    creds = USER_DB[uid]
    
    # Initialize Session
    if uid not in ACTIVE_SESSIONS:
        s = requests.Session()
        s.headers.update(HEADERS)
        ACTIVE_SESSIONS[uid] = s
    
    s = ACTIVE_SESSIONS[uid]
    
    # Always Try Login to be Safe
    try:
        r = s.get(BASE_URL + URLS['home'], allow_redirects=False, timeout=5)
        if r.status_code == 302 or "login" in r.headers.get("Location", ""):
            # Re-Login
            s.post(BASE_URL + URLS['login'], data={"user": creds['user'], "password": creds['pass']}, timeout=15)
    except:
        # Force Login on Error
        try: s.post(BASE_URL + URLS['login'], data={"user": creds['user'], "password": creds['pass']}, timeout=15)
        except: pass
        
    return s

# ====== 🌐 API FUNCTIONS ======

def api_create_client(session, name, password):
    try:
        session.get(BASE_URL + URLS['manage'], timeout=15)
        payload = {"subnme": name, "passwd1": password, "passwd2": password, "newcli": "1"}
        r = session.post(BASE_URL + URLS['manage'], data=payload, timeout=20)
        return r.status_code == 200
    except: return False

def api_get_clients_details(session):
    try:
        r = session.get(BASE_URL + URLS['manage'], timeout=20)
        soup = BeautifulSoup(r.text, "lxml")
        details = []
        for tr in soup.select("table tr"):
            tds = tr.find_all("td")
            if len(tds) > 3:
                row_txt = " | ".join([t.get_text(strip=True) for t in tds])
                if "User" not in row_txt and len(row_txt) > 5:
                    details.append(row_txt)
        return details
    except: return []

def api_get_allo_ranges(session):
    try:
        r = session.get(BASE_URL + URLS['allo'], timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        return [{"text": o.get_text(" ", strip=True), "value": o.get("value")} for o in soup.select("select[name=cdecode1] option") if o.get("value")]
    except: return []

def api_fetch_numbers(session, range_val, type_val):
    try:
        session.post(BASE_URL + URLS['allo'], data={"cdecode1": range_val, "selected1": "1", "cdecode": ""}, timeout=10)
        r = session.post(BASE_URL + URLS['allo'], data={"type": type_val, "selected1": "1", "selected2": "1", "cdecode": "", "cdecode1": range_val}, timeout=25)
        text = BeautifulSoup(r.text, "lxml").get_text(separator="\n")
        return list(set(re.findall(r'\b\d{7,16}\b', text)))
    except: return []

def api_get_simple_stats(session):
    try:
        r = session.get(BASE_URL + URLS['stats'], timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        stats = []
        for tr in soup.select("table tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                stats.append(f"🔹 <b>{tds[0].get_text(strip=True)}:</b> <code>{tds[1].get_text(strip=True)}</code>")
        return "\n".join(stats) if stats else "⚠️ No Data."
    except: return "❌ Error."

# ====== RECLAIM API ======
def api_get_rec_clients(session):
    try:
        r = session.get(BASE_URL + URLS["reclaim"], timeout=20)
        soup = BeautifulSoup(r.text, "lxml")
        return [(o.get_text(" ", strip=True), o.get("value")) for o in soup.select("select[name=idd] option") if o.get("value")]
    except: return []

def api_get_rec_ranges(session, cid):
    try:
        r = session.post(BASE_URL + URLS["reclaim"], data={"idd": cid}, timeout=20)
        soup = BeautifulSoup(r.text, "lxml")
        return [(o.get_text(" ", strip=True), o.get("value")) for o in soup.select("select[name=range] option") if o.get("value")]
    except: return []

def api_do_reclaim(session, cid, rng):
    try:
        r = session.post(BASE_URL + URLS["reclaim"], data={"idd": cid, "range": rng, "reclaim": "YES"}, timeout=20)
        return r.status_code == 200
    except: return False

# ====== 🤖 HANDLERS ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    
    # Auto-Owner Login
    if OWNER_TG_ID and uid == str(OWNER_TG_ID):
        USER_DB[uid] = {'user': ADMIN_USER, 'pass': ADMIN_PASS, 'name': OWNER_NAME, 'role': 'admin'}
    
    if uid in USER_DB:
        c = USER_DB[uid]
        await show_dashboard(update, c['name'], c['user'], c['role'])
        return ConversationHandler.END

    txt = (
        f"💫 <b>ASSALAM-O-ALAIKUM {user.first_name} JAAN!</b> 💫\n\n"
        f"🌹 <i>\"Tu Hazaar Bar Bhi Ruthe To Mana Lunga Tujhe,\n"
        f"Magar Dekh, Mohabbat Me Shamil Koi Dusra Na Ho..\"</i> 🌹\n\n"
        f"👑 <b>{OWNER_NAME}'s PRIVATE SERVER</b>\n"
        f"👇 <i>Request Access from Boss:</i>"
    )
    kb = [[InlineKeyboardButton("💖 SEND REQUEST", callback_data="req_login")]]
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def show_dashboard(update: Update, name, pid, role):
    rank = f"👑 {OWNER_NAME}" if role == 'admin' else "👤 𝐂𝐥𝐢𝐞𝐧𝐭"
    txt = (
        f"🔥 <b>MUDASIR VIP PANEL</b> 🔥\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Name:</b> {name}\n"
        f"🆔 <b>User ID:</b> <code>{pid}</code>\n"
        f"🔰 <b>Rank:</b> {rank}\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ <i>Select Action:</i>"
    )
    kb = []
    if role == 'admin':
        kb.append([InlineKeyboardButton("👤 Create New Client", callback_data="new_cli"), InlineKeyboardButton("♻️ Reclaim", callback_data="reclaim_start")])
        kb.append([InlineKeyboardButton("📋 View Clients", callback_data="view_cli")])
    
    kb.append([
        InlineKeyboardButton("🔢 Get Numbers", callback_data="get_num"),
        InlineKeyboardButton("📊 Stats", callback_data="view_stats")
    ])
    kb.append([InlineKeyboardButton("🔌 Logout", callback_data="logout")])
    
    if update.callback_query:
        await update.callback_query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    else:
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

# --- LOGIN REQUEST ---
async def request_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = update.effective_user.id
    if not OWNER_TG_ID: return
    context.bot_data[f"req_{uid}"] = update.effective_chat.id
    txt = f"🚨 <b>NEW LOVER AT DOOR!</b>\n👤 {update.effective_user.first_name} (`{uid}`)"
    kb = [[InlineKeyboardButton("✅ Approve", callback_data=f"ok_{uid}"), InlineKeyboardButton("❌ Reject", callback_data=f"no_{uid}")]]
    try: await context.bot.send_message(chat_id=OWNER_TG_ID, text=txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    except: pass
    await query.edit_message_text(f"✅ <b>Sent!</b>\n\n<i>Waiting for {OWNER_NAME}...</i> 💖", parse_mode="HTML")

async def admin_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    target = data.split("_")[1]
    if "no_" in data:
        await query.edit_message_text("❌ <b>Rejected.</b>", parse_mode="HTML")
        return ConversationHandler.END
    context.user_data['target_uid'] = target
    await query.edit_message_text("✍️ <b>Enter Portal User ID for him/her:</b>", parse_mode="HTML")
    return ADMIN_SET_ID

async def set_pid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_pid'] = update.message.text.strip()
    await update.message.reply_text("🔑 <b>Enter Password:</b>", parse_mode="HTML")
    return ADMIN_SET_PASS

async def set_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pw = update.message.text.strip()
    pid = context.user_data['new_pid']
    tid = context.user_data['target_uid']
    USER_DB[str(tid)] = {'user': pid, 'pass': pw, 'name': f"User {pid}", 'role': 'client'}
    origin = context.bot_data.get(f"req_{tid}", tid)
    welcome = (
        f"🎉 <b>CONGRATULATIONS SWEETHEART!</b> 🎉\n\n"
        f"👤 <b>Member:</b> <a href='tg://user?id={tid}'>User</a>\n"
        f"💖 <b>Status:</b> APPROVED by {OWNER_NAME}\n"
        f"🆔 <b>ID:</b> <code>{pid}</code>\n"
        f"🔑 <b>Pass:</b> <code>{pw}</code>\n\n"
        f"🚀 <i>You are now part of the Elite Team.</i>\n"
        f"Type /start to login."
    )
    try: await context.bot.send_message(chat_id=origin, text=welcome, parse_mode="HTML")
    except: pass
    await update.message.reply_text("✅ <b>Approved!</b>", parse_mode="HTML")
    return ConversationHandler.END

# --- CREATE CLIENT ---
async def create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🆕 <b>Enter New Client Name:</b>", parse_mode="HTML")
    return CREATE_NAME

async def create_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['cname'] = update.message.text.strip()
    await update.message.reply_text("🔑 <b>Set Password:</b>", parse_mode="HTML")
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
        await update.message.reply_text("❌ Mismatch. Try again.", parse_mode="HTML")
        return ConversationHandler.END
        
    msg = await update.message.reply_text("⚙️ <b>Creating Client...</b>", parse_mode="HTML")
    sess = get_session(update.effective_user.id)
    
    if api_create_client(sess, nm, orig):
        await msg.edit_text(f"✅ <b>BOOM! Client Created.</b>\n\n👤 <b>Name:</b> {nm}\n🔑 <b>Pass:</b> <code>{orig}</code>", parse_mode="HTML")
    else:
        await msg.edit_text("❌ <b>Failed.</b> Name might exist.", parse_mode="HTML")
    return ConversationHandler.END

# --- GET NUMBERS ---
async def num_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    await query.edit_message_text("⏳ <b>Logging In & Fetching...</b>", parse_mode="HTML")
    
    c = USER_DB.get(uid)
    if not c: return
    sess = get_session(uid)
    ranges = api_get_allo_ranges(sess)
    
    if not ranges:
        await query.edit_message_text("❌ <b>No Ranges Found.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
        return ConversationHandler.END
        
    context.user_data['n_ranges'] = ranges
    btns = [InlineKeyboardButton(r['text'], callback_data=f"n_{i}") for i, r in enumerate(ranges[:20])]
    chunks = [btns[i:i+1] for i in range(0, len(btns), 1)]
    chunks.append([InlineKeyboardButton("🔙 Cancel", callback_data="main_menu")])
    await query.edit_message_text("👇 <b>Select Country:</b>", reply_markup=InlineKeyboardMarkup(chunks), parse_mode="HTML")
    return NUM_STEP_1

async def num_rng_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("_")[1])
    context.user_data['n_rng'] = context.user_data['n_ranges'][idx]
    kb = [[InlineKeyboardButton("🔴 Not Active", callback_data="t_N")], [InlineKeyboardButton("🟢 Active", callback_data="t_A")]]
    await query.edit_message_text(f"🌍 <b>Selected:</b> {context.user_data['n_rng']['text']}\n👇 <b>Type:</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    return NUM_STEP_2

async def num_type_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    t = query.data.split("_")[1]
    await query.edit_message_text("🔎 <b>Extracting...</b>", parse_mode="HTML")
    
    sess = get_session(update.effective_user.id)
    rng = context.user_data['n_rng']['value']
    nums = api_fetch_numbers(sess, rng, t)
    
    if not nums:
        await query.edit_message_text("❌ <b>No Numbers Found.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
        return ConversationHandler.END
    
    context.user_data['n_res'] = nums
    sample = nums[0]
    detected = sample[:3]
    for c in ["380", "994", "62", "84", "92", "91", "44", "7"]:
        if sample.startswith(c) or sample.startswith("+"+c):
            detected = c; break
            
    kb = [[InlineKeyboardButton(f"With Code (+{detected}..)", callback_data="f_full")], [InlineKeyboardButton(f"Without Code", callback_data="f_cut")]]
    await query.edit_message_text(f"✅ <b>Found {len(nums)}!</b>\n📋 <b>Format?</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    return NUM_STEP_3

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
                    cut = True
                    break
            if not cut: final.append(clean)
        else: final.append(f"+{clean}")
            
    chunks = [final[i:i+50] for i in range(0, len(final), 50)]
    for c in chunks:
        msg = "\n".join([f"<code>{n}</code>" for n in c])
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode="HTML")
        await asyncio.sleep(0.3)
    
    with open("nums.txt", "w") as f: f.write("\n".join(final))
    await context.bot.send_document(chat_id=update.effective_chat.id, document=open("nums.txt", "rb"), caption=f"📂 <b>Full List</b>\n{BRAND}", parse_mode="HTML")
    os.remove("nums.txt")
    await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ <b>Finished.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
    return ConversationHandler.END

# --- RECLAIM ---
async def rec_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    if uid != OWNER_TG_ID: return
    
    await query.edit_message_text("♻️ <b>Fetching...</b>", parse_mode="HTML")
    sess = get_session(uid)
    clients = api_get_rec_clients(sess)
    
    if not clients:
        await query.edit_message_text("❌ No Clients.", parse_mode="HTML")
        return ConversationHandler.END
        
    context.user_data['rec_clients'] = clients
    btns = [InlineKeyboardButton(c[0], callback_data=f"rc_{i}") for i, c in enumerate(clients[:30])]
    chunks = [btns[i:i+2] for i in range(0, len(btns), 2)]
    chunks.append([InlineKeyboardButton("🔙 Cancel", callback_data="main_menu")])
    await query.edit_message_text("👇 <b>Select Client:</b>", reply_markup=InlineKeyboardMarkup(chunks), parse_mode="HTML")
    return REC_CLIENT

async def rec_cli_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("_")[1])
    cname, cid = context.user_data['rec_clients'][idx]
    context.user_data['rec_cid'] = cid
    await query.edit_message_text(f"♻️ <b>Client:</b> {cname}\n⏳ <b>Ranges...</b>", parse_mode="HTML")
    
    sess = get_session(update.effective_user.id)
    ranges = api_get_rec_ranges(sess, cid)
    
    if not ranges:
        await query.edit_message_text("❌ No Ranges Found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
        return ConversationHandler.END
    context.user_data['rec_rngs'] = ranges
    btns = [InlineKeyboardButton(r[0], callback_data=f"rr_{i}") for i, r in enumerate(ranges)]
    chunks = [btns[i:i+1] for i in range(0, len(btns), 1)]
    chunks.append([InlineKeyboardButton("🔙 Cancel", callback_data="main_menu")])
    await query.edit_message_text("👇 <b>Select Range:</b>", reply_markup=InlineKeyboardMarkup(chunks), parse_mode="HTML")
    return REC_RANGE

async def rec_rng_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    idx = int(query.data.split("_")[1])
    rname, rval = context.user_data['rec_rngs'][idx]
    context.user_data['rec_rval'] = rval
    kb = [[InlineKeyboardButton("✅ RECLAIM", callback_data="do_rec"), InlineKeyboardButton("❌ CANCEL", callback_data="main_menu")]]
    await query.edit_message_text(f"⚠️ <b>CONFIRM?</b>\nRange: {rname}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    return REC_CONFIRM

async def rec_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "main_menu":
        await menu(update, context)
        return ConversationHandler.END
    
    await query.edit_message_text("⚙️ <b>Processing...</b>", parse_mode="HTML")
    sess = get_session(update.effective_user.id)
    
    if api_do_reclaim(sess, context.user_data['rec_cid'], context.user_data['rec_rval']):
        await query.edit_message_text("✅ <b>SUCCESS! Reclaimed.</b> 💖", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
    else:
        await query.edit_message_text("❌ <b>Failed.</b>", parse_mode="HTML")
    return ConversationHandler.END

# --- EXTRAS ---
async def view_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    uid = str(update.effective_user.id)
    await query.edit_message_text("⏳ <b>Fetching...</b>", parse_mode="HTML")
    sess = get_session(uid)
    txt = api_get_simple_stats(sess)
    await query.edit_message_text(f"📊 <b>TODAY'S REPORT</b>\n━━━━━━━━━━━━\n{txt}\n━━━━━━━━━━━━", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")

async def view_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("⏳ <b>Loading...</b>", parse_mode="HTML")
    sess = get_session(update.effective_user.id)
    clients = api_get_clients_details(sess)
    
    if not clients:
        await query.edit_message_text("⚠️ None Found.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
        return
        
    with open("clients.txt", "w") as f: f.write("\n".join(clients))
    await context.bot.send_document(chat_id=update.effective_chat.id, document=open("clients.txt", "rb"), caption="📋 Clients")
    os.remove("clients.txt")
    await menu(update, context)

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        f"📚 <b>HELP CENTER</b>\n\n"
        f"📌 <b>/start</b> - Dashboard\n"
        f"📌 <b>/create</b> - New Client\n"
        f"📌 <b>/num</b> - Scrape Numbers\n"
        f"📌 <b>/clients</b> - List\n"
        f"📌 <b>/help</b> - This Menu\n\n"
        f"{BRAND}"
    )
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
    else:
        await update.message.reply_text(text, parse_mode="HTML")

async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid in USER_DB: del USER_DB[uid]
    if uid in ACTIVE_SESSIONS: del ACTIVE_SESSIONS[uid]
    await update.callback_query.edit_message_text("🔒 <b>Logged Out.</b>", parse_mode="HTML")
    return ConversationHandler.END

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid in USER_DB:
        c = USER_DB[uid]
        await show_dashboard(update.callback_query.message, c['name'], c['user'], c['role'])
    else: await update.callback_query.edit_message_text("Expired. /start")
    return ConversationHandler.END

def main():
    if not BOT_TOKEN: return
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("create", create_start))
    app.add_handler(CommandHandler("clients", view_clients))
    app.add_handler(CommandHandler("num", num_start))
    
    app.add_handler(CallbackQueryHandler(request_login, pattern="req_login"))
    app.add_handler(CallbackQueryHandler(view_clients, pattern="view_cli"))
    app.add_handler(CallbackQueryHandler(view_stats, pattern="view_stats"))
    app.add_handler(CallbackQueryHandler(help_cmd, pattern="help_cmd"))
    app.add_handler(CallbackQueryHandler(logout, pattern="logout"))
    app.add_handler(CallbackQueryHandler(menu, pattern="main_menu"))

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
            NUM_STEP_1: [CallbackQueryHandler(num_rng_sel, pattern="^n_")],
            NUM_STEP_2: [CallbackQueryHandler(num_type_sel, pattern="^t_")],
            NUM_STEP_3: [CallbackQueryHandler(num_fmt_sel, pattern="^f_")]
        },
        fallbacks=[CallbackQueryHandler(menu, pattern="main_menu")]
    ))
    
    app.add_handler(ConversationHandler(
        entry_points=[CallbackQueryHandler(rec_start, pattern="reclaim_start")],
        states={
            RECLAIM_STEP_1: [CallbackQueryHandler(rec_cli_sel, pattern="^rc_")],
            RECLAIM_STEP_2: [CallbackQueryHandler(rec_rng_sel, pattern="^rr_")],
            RECLAIM_CONFIRM: [CallbackQueryHandler(rec_do, pattern="^(do_rec|main_menu)")]
        },
        fallbacks=[CallbackQueryHandler(menu, pattern="main_menu")]
    ))

    print("BOT STARTED...")
    app.run_polling()

if __name__ == "__main__":
    main()
