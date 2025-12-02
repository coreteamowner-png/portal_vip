import logging
import os
import requests
import re
import json
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes, ConversationHandler

# ====== ⚙️ CONFIG ======
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_TG_ID = os.getenv("OWNER_ID") 
OWNER_NAME = "Mudasir"
BRAND = "🔥 𝗣𝗢𝗪𝗘𝗥𝗘𝗗 𝗕𝗬 𝗠𝗨𝗗𝗔𝗦𝗜𝗥 𝗧𝗘𝗖𝗛 🔥"

# 👑 ADMIN CREDS
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

# 📱 HEADERS (Simple Android)
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded"
}

# 💾 DATA
SESSION_FILE = "sessions.json"
USER_DB = {} # {uid: {'user':, 'pass':, 'name':, 'role':}}

# 🚦 STATES
(CREATE_NAME, CREATE_PASS, CREATE_CONFIRM,
 ADMIN_SET_ID, ADMIN_SET_PASS,
 RECLAIM_STEP_1, RECLAIM_STEP_2, RECLAIM_CONFIRM,
 NUM_STEP_1, NUM_STEP_2, NUM_STEP_3) = range(11)

logging.basicConfig(level=logging.INFO)

# ====== 🛠️ HELPERS ======

def load_db():
    global USER_DB
    if os.path.exists(SESSION_FILE):
        try:
            with open(SESSION_FILE, "r") as f: USER_DB = json.load(f)
        except: pass

def save_db():
    try:
        with open(SESSION_FILE, "w") as f: json.dump(USER_DB, f)
    except: pass

load_db()

# ====== 🌐 THE ENGINE (FRESH LOGIN PER REQUEST) ======

def execute_portal_action(username, password, action_type, data=None):
    """
    Logs in fresh, performs action, returns result.
    action_type: 'get_ranges', 'fetch_nums', 'stats', 'create_cli', 'reclaim_list', 'reclaim_do'
    """
    s = requests.Session()
    s.headers.update(HEADERS)
    
    try:
        # 1. LOGIN
        l = s.post(BASE_URL + URLS["login"], data={"user": username, "password": password}, timeout=20)
        if "opt=shw_all" not in l.url and "log out" not in l.text.lower():
            return {"status": False, "msg": "Login Failed"}

        # 2. PERFORM ACTION
        
        # --- GET NUMBERS RANGES ---
        if action_type == 'get_ranges':
            r = s.get(BASE_URL + URLS["allo"], timeout=15)
            soup = BeautifulSoup(r.text, "lxml")
            opts = soup.select("select[name=cdecode1] option")
            res = [{"text": o.get_text(" ", strip=True), "value": o.get("value")} for o in opts if o.get("value")]
            return {"status": True, "data": res}

        # --- FETCH NUMBERS ---
        elif action_type == 'fetch_nums':
            # Step 1: Select Range
            s.post(BASE_URL + URLS["allo"], data={"cdecode1": data['rng'], "selected1": "1", "cdecode": ""}, timeout=15)
            # Step 2: Get List
            r = s.post(BASE_URL + URLS["allo"], data={"type": data['type'], "selected1": "1", "selected2": "1", "cdecode": "", "cdecode1": data['rng']}, timeout=30)
            text = BeautifulSoup(r.text, "lxml").get_text(separator="\n")
            nums = list(set(re.findall(r'\b\d{7,16}\b', text)))
            return {"status": True, "data": nums}

        # --- TODAY STATS ---
        elif action_type == 'stats':
            r = s.get(BASE_URL + URLS["stats"], timeout=15)
            soup = BeautifulSoup(r.text, "lxml")
            stats = []
            for tr in soup.select("table tr"):
                tds = tr.find_all("td")
                if len(tds) >= 2:
                    stats.append(f"🔹 <b>{tds[0].get_text(strip=True)}:</b> {tds[1].get_text(strip=True)}")
            
            if not stats: # Fallback
                txt = soup.get_text()
                for line in txt.splitlines():
                    if "Total" in line or "Sent" in line: stats.append(f"🔸 {line.strip()}")
            return {"status": True, "data": "\n".join(stats)}

        # --- CREATE CLIENT ---
        elif action_type == 'create_cli':
            s.get(BASE_URL + URLS["manage"], timeout=10)
            payload = {"subnme": data['name'], "passwd1": data['pass'], "passwd2": data['pass'], "newcli": "1"}
            r = s.post(BASE_URL + URLS["manage"], data=payload, timeout=20)
            if data['name'] in r.text or r.status_code == 200:
                return {"status": True}
            return {"status": False}

        # --- RECLAIM LIST ---
        elif action_type == 'rec_list':
            r = s.get(BASE_URL + URLS["reclaim"], timeout=15)
            soup = BeautifulSoup(r.text, "lxml")
            clients = [(o.get_text(" ", strip=True), o.get("value")) for o in soup.select("select[name=idd] option") if o.get("value")]
            return {"status": True, "data": clients}

        # --- RECLAIM RANGES ---
        elif action_type == 'rec_ranges':
            r = s.post(BASE_URL + URLS["reclaim"], data={"idd": data['cid']}, timeout=15)
            soup = BeautifulSoup(r.text, "lxml")
            ranges = [(o.get_text(" ", strip=True), o.get("value")) for o in soup.select("select[name=range] option") if o.get("value")]
            return {"status": True, "data": ranges}

        # --- RECLAIM DO ---
        elif action_type == 'rec_do':
            r = s.post(BASE_URL + URLS["reclaim"], data={"idd": data['cid'], "range": data['rng'], "reclaim": "YES"}, timeout=20)
            return {"status": True}

    except Exception as e:
        return {"status": False, "msg": str(e)}
    
    return {"status": False, "msg": "Unknown Error"}

# ====== 🤖 BOT LOGIC ======

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    uid = str(user.id)
    
    # Auto Owner
    if OWNER_TG_ID and uid == str(OWNER_TG_ID):
        USER_DB[uid] = {'user': ADMIN_USER, 'pass': ADMIN_PASS, 'name': OWNER_NAME, 'role': 'admin'}
        save_db()
    
    if uid in USER_DB:
        c = USER_DB[uid]
        await show_dashboard(update, c['name'], c['user'], c['role'])
        return ConversationHandler.END

    txt = (
        f"💫 <b>ASSALAM-O-ALAIKUM {user.first_name} JAAN!</b> 💫\n\n"
        f"🌹 <i>\"Tu Hazaar Bar Bhi Ruthe To Mana Lunga Tujhe,\n"
        f"Magar Dekh, Mohabbat Me Shamil Koi Dusra Na Ho..\"</i> 🌹\n\n"
        f"👑 <b>{OWNER_NAME}'s PRIVATE SERVER</b>\n"
        f"🔒 <b>Status:</b> <code>SECURE</code>\n"
        f"👇 <i>Request Access from Boss:</i>"
    )
    kb = [[InlineKeyboardButton("💖 SEND REQUEST", callback_data="req_login")]]
    await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

async def show_dashboard(update, name, pid, role):
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
        kb.append([InlineKeyboardButton("👤 Create Client", callback_data="new_cli"), InlineKeyboardButton("♻️ Bulk Reclaim", callback_data="rec_start")])
    
    kb.append([InlineKeyboardButton("🔢 Get Numbers", callback_data="get_num"), InlineKeyboardButton("📊 Today Stats", callback_data="view_stats")])
    kb.append([InlineKeyboardButton("🔌 Logout", callback_data="logout")])
    
    if hasattr(update, 'callback_query') and update.callback_query:
        await update.callback_query.edit_message_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    else:
        await update.message.reply_text(txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")

# --- LOGIN REQUEST ---
async def req_login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = update.effective_user.id
    if not OWNER_TG_ID: return
    context.bot_data[f"req_{uid}"] = update.effective_chat.id
    
    txt = f"🚨 <b>NEW REQUEST!</b>\n👤 {update.effective_user.first_name} (`{uid}`)"
    kb = [[InlineKeyboardButton("✅ Accept", callback_data=f"ok_{uid}"), InlineKeyboardButton("❌ Reject", callback_data=f"no_{uid}")]]
    try: await context.bot.send_message(chat_id=OWNER_TG_ID, text=txt, reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    except: pass
    await query.edit_message_text("✅ <b>Sent!</b> Waiting for Approval 💖", parse_mode="HTML")

async def admin_verify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    target = data.split("_")[1]
    if "no_" in data:
        await query.edit_message_text("❌ Rejected.")
        return ConversationHandler.END
    context.user_data['target_uid'] = target
    await query.edit_message_text("✍️ <b>Enter Portal ID:</b>", parse_mode="HTML")
    return ADMIN_SET_ID

async def set_pid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['new_pid'] = update.message.text.strip()
    await update.message.reply_text("🔑 <b>Enter Password:</b>", parse_mode="HTML")
    return ADMIN_SET_PASS

async def set_pass(update: Update, context: ContextTypes.DEFAULT_TYPE):
    pw = update.message.text.strip()
    pid = context.user_data['new_pid']
    tid = context.user_data['target_uid']
    
    # Verify by Login
    res = execute_portal_action(pid, pw, 'stats') # dummy check
    if res['status']:
        USER_DB[str(tid)] = {'user': pid, 'pass': pw, 'name': f"User {pid}", 'role': 'client'}
        save_db()
        # Notify
        origin = context.bot_data.get(f"req_{tid}", tid)
        welcome = f"🎉 <b>APPROVED!</b>\n🆔 <code>{pid}</code>\n🔑 <code>{pw}</code>\n\n🚀 <i>Welcome Sweetheart!</i>\nType /start"
        try: await context.bot.send_message(chat_id=origin, text=welcome, parse_mode="HTML")
        except: pass
        await update.message.reply_text("✅ <b>Done!</b>", parse_mode="HTML")
    else:
        await update.message.reply_text("❌ <b>Invalid Creds!</b>", parse_mode="HTML")
    return ConversationHandler.END

# --- GET NUMBERS ---
async def num_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    await query.edit_message_text("⏳ <b>Fetching Ranges...</b>", parse_mode="HTML")
    
    c = USER_DB[uid]
    res = execute_portal_action(c['user'], c['pass'], 'get_ranges')
    
    if not res['status'] or not res['data']:
        await query.edit_message_text("❌ <b>No Ranges Found / Login Failed.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
        return ConversationHandler.END
        
    context.user_data['n_ranges'] = res['data']
    btns = [InlineKeyboardButton(r['text'], callback_data=f"n_{i}") for i, r in enumerate(res['data'][:20])]
    chunks = [btns[i:i+1] for i in range(0, len(btns), 1)]
    chunks.append([InlineKeyboardButton("🔙 Cancel", callback_data="main_menu")])
    await query.edit_message_text("👇 <b>Select Country:</b>", reply_markup=InlineKeyboardMarkup(chunks), parse_mode="HTML")
    return NUM_STEP_1

async def num_rng_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    idx = int(query.data.split("_")[1])
    context.user_data['n_rng'] = context.user_data['n_ranges'][idx]
    kb = [[InlineKeyboardButton("🔴 Not Active", callback_data="t_N")], [InlineKeyboardButton("🟢 Active", callback_data="t_A")]]
    await query.edit_message_text(f"🌍 <b>Selected:</b> {context.user_data['n_rng']['text']}\n👇 <b>Type:</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    return NUM_STEP_2

async def num_type_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    t = query.data.split("_")[1]
    await query.edit_message_text("🔎 <b>Extracting...</b>", parse_mode="HTML")
    
    uid = str(update.effective_user.id)
    c = USER_DB[uid]
    data = {'rng': context.user_data['n_rng']['value'], 'type': t}
    res = execute_portal_action(c['user'], c['pass'], 'fetch_nums', data)
    
    if not res['status'] or not res['data']:
        await query.edit_message_text("❌ <b>No Numbers Found.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
        return ConversationHandler.END
    
    context.user_data['n_res'] = res['data']
    sample = res['data'][0]
    detected = sample[:3]
    kb = [[InlineKeyboardButton(f"With Code (+{detected}..)", callback_data="f_full")], [InlineKeyboardButton(f"Without Code", callback_data="f_cut")]]
    await query.edit_message_text(f"✅ <b>Found {len(res['data'])}!</b>\n📋 <b>Format?</b>", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    return NUM_STEP_3

async def num_fmt_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
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
            
    # Send Chat
    chunks = [final[i:i+50] for i in range(0, len(final), 50)]
    for chunk in chunks:
        msg = "\n".join([f"<code>{n}</code>" for n in chunk])
        await context.bot.send_message(chat_id=update.effective_chat.id, text=msg, parse_mode="HTML")
    
    # Send File
    with open("nums.txt", "w") as f: f.write("\n".join(final))
    await context.bot.send_document(chat_id=update.effective_chat.id, document=open("nums.txt", "rb"), caption=f"📂 <b>List</b>\n{BRAND}", parse_mode="HTML")
    os.remove("nums.txt")
    await context.bot.send_message(chat_id=update.effective_chat.id, text="✅ <b>Finished.</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
    return ConversationHandler.END

# --- STATS ---
async def view_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    uid = str(update.effective_user.id)
    c = USER_DB[uid]
    await query.edit_message_text("⏳ <b>Fetching...</b>", parse_mode="HTML")
    res = execute_portal_action(c['user'], c['pass'], 'stats')
    txt = res['data'] if res['status'] else "Error."
    await query.edit_message_text(f"📊 <b>TODAY'S REPORT</b>\n━━━━━━━━━━━━\n{txt}\n━━━━━━━━━━━━", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")

# --- CREATE CLIENT ---
async def create_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("🆕 <b>Enter Name:</b>", parse_mode="HTML")
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
    if conf != context.user_data['cpass']:
        await update.message.reply_text("❌ Mismatch.")
        return ConversationHandler.END
    
    msg = await update.message.reply_text("⚙️ <b>Creating...</b>", parse_mode="HTML")
    res = execute_portal_action(ADMIN_USER, ADMIN_PASS, 'create_cli', {'name': context.user_data['cname'], 'pass': conf})
    
    if res['status']: await msg.edit_text("✅ <b>Client Created!</b>", parse_mode="HTML")
    else: await msg.edit_text("❌ <b>Failed.</b>", parse_mode="HTML")
    return ConversationHandler.END

# --- RECLAIM ---
async def rec_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.edit_message_text("♻️ <b>Fetching...</b>", parse_mode="HTML")
    res = execute_portal_action(ADMIN_USER, ADMIN_PASS, 'rec_list')
    if not res['status'] or not res['data']:
        await update.callback_query.edit_message_text("❌ No Clients.", parse_mode="HTML")
        return ConversationHandler.END
    
    context.user_data['rec_clients'] = res['data']
    btns = [InlineKeyboardButton(c[0], callback_data=f"rc_{i}") for i, c in enumerate(res['data'][:30])]
    chunks = [btns[i:i+2] for i in range(0, len(btns), 2)]
    chunks.append([InlineKeyboardButton("🔙 Cancel", callback_data="main_menu")])
    await update.callback_query.edit_message_text("👇 <b>Select Client:</b>", reply_markup=InlineKeyboardMarkup(chunks), parse_mode="HTML")
    return REC_CLIENT

async def rec_cli_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    idx = int(query.data.split("_")[1])
    cname, cid = context.user_data['rec_clients'][idx]
    context.user_data['rec_cid'] = cid
    await query.edit_message_text(f"♻️ <b>Client:</b> {cname}\n⏳ <b>Ranges...</b>", parse_mode="HTML")
    
    res = execute_portal_action(ADMIN_USER, ADMIN_PASS, 'rec_ranges', {'cid': cid})
    if not res['status'] or not res['data']:
        await query.edit_message_text("❌ No Ranges.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
        return ConversationHandler.END
    
    context.user_data['rec_rngs'] = res['data']
    btns = [InlineKeyboardButton(r[0], callback_data=f"rr_{i}") for i, r in enumerate(res['data'])]
    chunks = [btns[i:i+1] for i in range(0, len(btns), 1)]
    chunks.append([InlineKeyboardButton("🔙 Cancel", callback_data="main_menu")])
    await query.edit_message_text("👇 <b>Select Range:</b>", reply_markup=InlineKeyboardMarkup(chunks), parse_mode="HTML")
    return REC_RANGE

async def rec_rng_sel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    idx = int(query.data.split("_")[1])
    rname, rval = context.user_data['rec_rngs'][idx]
    context.user_data['rec_rval'] = rval
    kb = [[InlineKeyboardButton("✅ RECLAIM", callback_data="do_rec"), InlineKeyboardButton("❌ CANCEL", callback_data="main_menu")]]
    await query.edit_message_text(f"⚠️ <b>CONFIRM?</b>\nRange: {rname}", reply_markup=InlineKeyboardMarkup(kb), parse_mode="HTML")
    return REC_CONFIRM

async def rec_do(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.data == "main_menu":
        await menu(update, context)
        return ConversationHandler.END
    await query.edit_message_text("⚙️ <b>Processing...</b>", parse_mode="HTML")
    res = execute_portal_action(ADMIN_USER, ADMIN_PASS, 'rec_do', {'cid': context.user_data['rec_cid'], 'rng': context.user_data['rec_rval']})
    if res['status']: await query.edit_message_text("✅ <b>SUCCESS!</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="main_menu")]]), parse_mode="HTML")
    else: await query.edit_message_text("❌ <b>Failed.</b>", parse_mode="HTML")
    return ConversationHandler.END

# --- COMMON ---
async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid in USER_DB: del USER_DB[uid]; save_db()
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
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(request_login, pattern="req_login"))
    app.add_handler(CallbackQueryHandler(view_stats, pattern="view_stats"))
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
            REC_CLIENT: [CallbackQueryHandler(rec_cli_sel, pattern="^rc_")],
            REC_RANGE: [CallbackQueryHandler(rec_rng_sel, pattern="^rr_")],
            REC_CONFIRM: [CallbackQueryHandler(rec_do, pattern="^(do_rec|main_menu)")]
        },
        fallbacks=[CallbackQueryHandler(menu, pattern="main_menu")]
    ))

    print("BOT STARTED...")
    app.run_polling()

if __name__ == "__main__":
    main()
