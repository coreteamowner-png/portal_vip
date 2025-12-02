from flask import Flask, render_template, request, jsonify, session, redirect, url_for
import requests
import re
import os
from bs4 import BeautifulSoup

app = Flask(__name__)
app.secret_key = os.urandom(24)

# CONFIG
ADMIN_USER = "7944"
ADMIN_PASS = "10-16-2025@Swi"
BASE_URL = "http://mysmsportal.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 10; K) Chrome/142.0.0.0 Mobile Safari/537.36",
    "Content-Type": "application/x-www-form-urlencoded"
}

# --- HELPERS ---
def get_sess():
    s = requests.Session()
    s.headers.update(HEADERS)
    return s

def smart_login(user, password):
    s = get_sess()
    try:
        r = s.post(f"{BASE_URL}/index.php?login=1", data={"user": user, "password": password}, timeout=15)
        if "opt=shw_all" in r.url or "log out" in r.text.lower():
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
    
    # Verify
    s = smart_login(u, p)
    if s:
        session['user'] = u
        session['pass'] = p
        session['role'] = 'admin' if u == ADMIN_USER else 'client'
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "msg": "Invalid Credentials"})

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user' not in session: return redirect(url_for('index'))
    return render_template('dashboard.html', user=session['user'], role=session['role'])

# --- API ENDPOINTS (AJAX) ---

@app.route('/api/stats', methods=['POST'])
def get_stats():
    s = smart_login(session['user'], session['pass'])
    if not s: return jsonify({"status": "error", "msg": "Session Expired"})
    
    try:
        r = s.get(f"{BASE_URL}/index.php?opt=shw_sts_today_sum")
        soup = BeautifulSoup(r.text, "lxml")
        data = []
        # Table parsing
        for tr in soup.select("table tr"):
            tds = tr.find_all("td")
            if len(tds) >= 2:
                data.append({"key": tds[0].get_text(strip=True), "val": tds[1].get_text(strip=True)})
        
        # Fallback text parsing
        if not data:
            txt = soup.get_text()
            for line in txt.splitlines():
                if "Total" in line or "Sent" in line:
                    data.append({"key": "Info", "val": line.strip()})
                    
        return jsonify({"status": "success", "data": data})
    except Exception as e:
        return jsonify({"status": "error", "msg": str(e)})

@app.route('/api/get_ranges', methods=['POST'])
def get_ranges():
    s = smart_login(session['user'], session['pass'])
    if not s: return jsonify({"status": "error"})
    
    try:
        r = s.get(f"{BASE_URL}/index.php?opt=shw_allo")
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
        # Step 1
        s.post(f"{BASE_URL}/index.php?opt=shw_allo", data={"cdecode1": rng, "selected1": "1", "cdecode": ""})
        # Step 2
        r = s.post(f"{BASE_URL}/index.php?opt=shw_allo", data={"type": typ, "selected1": "1", "selected2": "1", "cdecode": "", "cdecode1": rng})
        
        txt = BeautifulSoup(r.text, "lxml").get_text(separator="\n")
        nums = list(set(re.findall(r'\b\d{7,16}\b', txt)))
        return jsonify({"status": "success", "data": nums})
    except: return jsonify({"status": "error", "msg": "Failed"})

@app.route('/api/create_client', methods=['POST'])
def create_client():
    if session.get('role') != 'admin': return jsonify({"status": "error", "msg": "Unauthorized"})
    
    data = request.json
    name = data.get('name')
    pw = data.get('pass')
    
    s = smart_login(session['user'], session['pass'])
    try:
        s.get(f"{BASE_URL}/index.php?opt=shw_mge")
        payload = {"subnme": name, "passwd1": pw, "passwd2": pw, "newcli": "1"}
        r = s.post(f"{BASE_URL}/index.php?opt=shw_mge", data=payload)
        
        if name in r.text: return jsonify({"status": "success"})
        else: return jsonify({"status": "error", "msg": "Failed (Name exists?)"})
    except: return jsonify({"status": "error"})

if __name__ == "__main__":
    app.run(debug=True)
