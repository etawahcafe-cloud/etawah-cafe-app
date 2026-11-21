import hashlib
import hmac
import json
import os
import re
import sqlite3
from pathlib import Path

import requests
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, Response, abort, g, jsonify, render_template_string, request, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from io import BytesIO

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 17 * 1024 * 1024
limit = Limiter(get_remote_address, app=app, storage_uri=os.getenv('RATE_STORAGE', 'memory://'))
store = Path(os.environ['DATA_DIR'])
store.mkdir(parents=True, exist_ok=True)
cipher = Fernet(os.environ['DATA_KEY'])
admin_pass = os.environ['ADMIN_PASSWORD']
if len(admin_pass) < 16:
    raise ValueError('ADMIN_PASSWORD requires at least 16 characters')
auth = (os.environ['RAZORPAY_KEY_ID'], os.environ['RAZORPAY_KEY_SECRET'])
names = dict(income='आय प्रमाण पत्र', caste='जाति प्रमाण पत्र', domicile='निवास प्रमाण पत्र', pan='नया पैन कार्ड', correction='पैन सुधार')
prices = dict(income=8000, caste=8000, domicile=8000, pan=15000, correction=15000)
schema = """CREATE TABLE IF NOT EXISTS cases(
 id TEXT PRIMARY KEY, token TEXT UNIQUE, service TEXT, amount INTEGER,
 details BLOB, link TEXT, url TEXT, paid INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS docs(record TEXT, seq INTEGER, mime TEXT, data BLOB,
 PRIMARY KEY(record,seq));"""
with sqlite3.connect(store / 'cases.db') as initial:
    initial.executescript(schema)

def db():
    if 'db' not in g:
        g.db = sqlite3.connect(store / 'cases.db', timeout=30)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close(error):
    if 'db' in g:
        g.db.close()

@app.after_request
def headers(r):
    r.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY'})
    return r

@app.get('/')
def home():
    return send_file(Path(__file__).with_name('index.html'))

def otp_mobile():
    value = (request.get_json(silent=True) or {}).get('mobile', '')
    if not isinstance(value, str) or not re.fullmatch('[6-9][0-9]{9}', value):
        abort(400)
    return value

def verify_api(operation, mobile, **fields):
    service = os.getenv('TWILIO_VERIFY_SERVICE_SID')
    credentials = (os.getenv('TWILIO_ACCOUNT_SID'), os.getenv('TWILIO_AUTH_TOKEN'))
    if not service or not all(credentials):
        abort(503)
    try:
        response = requests.post(f'https://verify.twilio.com/v2/Services/{service}/{operation}',
            auth=credentials, data=dict(To='+91'+mobile, **fields), timeout=12)
        if response.status_code == 429:
            abort(429)
        if operation == 'VerificationCheck' and response.status_code in (400,404):
            abort(403)
        response.raise_for_status()
        return response.json().get('status')
    except (requests.RequestException, ValueError):
        abort(503)

@app.post('/login/send')
@limit.limit('6/hour')
@limit.limit('1/minute', key_func=otp_mobile)
def send_code():
    if verify_api('Verifications', otp_mobile(), Channel='sms') != 'pending':
        abort(503)
    return jsonify(ok=True)

@app.post('/login/check')
@limit.limit('20/hour')
@limit.limit('8/10 minutes', key_func=otp_mobile)
def check_code():
    mobile = otp_mobile()
    code = request.json.get('code','')
    if not isinstance(code,str) or not re.fullmatch('[0-9]{6}',code):
        abort(400)
    if verify_api('VerificationCheck',mobile,Code=code) != 'approved':
        abort(403)
    response = jsonify(ok=True)
    response.set_cookie('ec_login', cipher.encrypt(('login:'+mobile).encode()).decode(),
                        secure=True, httponly=True, samesite='Strict', max_age=86400)
    return response

@app.before_request
def authenticate():
    if request.endpoint in ('fees','apply','status','pay'):
        try:
            identity = cipher.decrypt(request.cookies.get('ec_login','').encode(),ttl=86400).decode()
        except InvalidToken:
            abort(401)
        if not re.fullmatch(r'login:[6-9][0-9]{9}',identity):
            abort(401)
        g.mobile = identity[6:]

@app.get('/fees')
def fees():
    return jsonify(prices)

def token_hash():
    token = request.headers.get('X-Application-Key','')
    if not re.fullmatch('[0-9a-f]{64}',token):
        abort(403)
    return hashlib.sha256(token.encode()).hexdigest()

def current():
    row = db().execute('SELECT * FROM cases WHERE token=?',(token_hash(),)).fetchone()
    if row and json.loads(cipher.decrypt(row['details']))['mobile'] != g.mobile:
        abort(403)
    return row

@app.post('/apply')
@limit.limit('15/hour')
def apply():
    key = token_hash()
    existing = current()
    if existing:
        return jsonify(id=existing['id'])
    f = request.form
    service = f.get('service','')
    if service not in names or f.get('consent') != 'yes' or f.get('fee') != str(prices[service]):
        abort(400)
    fields = {k:f.get(k,'').strip() for k in ('name','mobile','address','detail')}
    if fields['mobile'] != g.mobile:
        abort(403)
    if not (2 <= len(fields['name']) <= 100 and re.fullmatch('[6-9][0-9]{9}',fields['mobile']) and 5 <= len(fields['address']) <= 500 and 1 <= len(fields['detail']) <= 500):
        abort(400)
    uploads = request.files.getlist('docs')
    if not 1 <= len(uploads) <= 4:
        abort(400)
    items = []
    for file in uploads:
        data = file.read(4*1024*1024+1)
        mime = next((m for prefix,m in [(b'%PDF-','application/pdf'),(b'\xff\xd8\xff','image/jpeg'),(b'\x89PNG\r\n\x1a\n','image/png')] if data.startswith(prefix)),None)
        if not mime or len(data)>4*1024*1024:
            abort(400)
        items.append((mime,cipher.encrypt(data)))
    ref = 'EC-' + os.urandom(8).hex().upper()
    with db():
        saved = db().execute('INSERT OR IGNORE INTO cases(id,token,service,amount,details) VALUES(?,?,?,?,?)',(ref,key,service,prices[service],cipher.encrypt(json.dumps(fields).encode())))
        if saved.rowcount:
            db().executemany('INSERT INTO docs VALUES(?,?,?,?)',[(ref,i,m,b) for i,(m,b) in enumerate(items)])
    return jsonify(id=current()['id'])

API = 'https://api.razorpay.com/v1/payment_links'
def gateway(method,path='',**kw):
    try:
        r = requests.request(method,API+path,auth=auth,timeout=12,**kw)
        r.raise_for_status()
        return r.json()
    except (ValueError,requests.RequestException):
        abort(503)

def refresh_payment(row):
    if row['link'] and not row['paid']:
        p = gateway('GET','/'+row['link'])
        if p.get('id') == row['link'] and p.get('reference_id') == row['id'] and p.get('currency') == 'INR' and p.get('amount_paid') == p.get('amount') == row['amount'] and p.get('status') == 'paid':
            with db():
                db().execute('UPDATE cases SET paid=1 WHERE id=?',(row['id'],))

@app.cli.command('reconcile')
def reconcile():
    for row in db().execute('SELECT * FROM cases WHERE paid=0 AND link IS NOT NULL').fetchall():
        refresh_payment(row)

@app.post('/status')
@limit.limit('60/minute')
def status():
    row = current()
    if not row:
        abort(404)
    refresh_payment(row)
    row = current()
    return jsonify(id=row['id'],paid=bool(row['paid']),amount=row['amount'],service=row['service'])

@app.post('/pay')
@limit.limit('15/minute')
def pay():
    row = current()
    if not row or row['paid']:
        abort(409)
    if row['url']:
        return jsonify(url=row['url'])
    # Unique provider reference also allows recovery after a timed-out creation.
    matches = gateway('GET',params={'reference_id':row['id']}).get('payment_links',[])
    p = next((x for x in matches if x.get('reference_id') == row['id']),None)
    if p is None:
        p = gateway('POST',json=dict(amount=row['amount'],currency='INR',accept_partial=False,reference_id=row['id'],description='Etawah Cafe application '+row['id']))
    if p.get('reference_id') != row['id'] or p.get('amount') != row['amount'] or p.get('currency') != 'INR' or not p.get('short_url','').startswith('https://'):
        abort(502)
    with db():
        db().execute('UPDATE cases SET link=?,url=? WHERE id=?',(p['id'],p['short_url'],row['id']))
    return jsonify(url=p['short_url'])

def staff():
    a = request.authorization
    if not a or a.username != 'cafe' or not hmac.compare_digest((a.password or '').encode(),admin_pass.encode()):
        abort(Response('Staff login required',401,{'WWW-Authenticate':'Basic realm="Etawah Cafe"'}))

@app.get('/staff')
@limit.limit('60/minute')
def inbox():
    staff()
    rows = []
    for row in db().execute('SELECT * FROM cases ORDER BY rowid DESC'):
        detail=json.loads(cipher.decrypt(row['details']))
        docs=db().execute('SELECT seq FROM docs WHERE record=? ORDER BY seq',(row['id'],)).fetchall()
        rows.append((row,detail,docs))
    return render_template_string("""<meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>Etawah Cafe • आवेदन</title><h1>आवेदन</h1>{% for r,d,files in rows %}<article><h2>{{names[r.service]}} · {{r.id}}</h2><p>{{d.name}} · {{d.mobile}}<p>{{d.address}}<p>{{d.detail}}<p>₹{{r.amount/100}} · {{'भुगतान सत्यापित' if r.paid else 'पुष्टि लंबित'}}{% for f in files %} <a href="/staff/{{r.id}}/{{f.seq}}">दस्तावेज़ {{loop.index}}</a>{% endfor %}</article>{% else %}अभी कोई आवेदन नहीं है।{% endfor %}""",rows=rows,names=names)

@app.get('/staff/<ref>/<int:seq>')
@limit.limit('60/minute')
def download(ref,seq):
    staff()
    d=db().execute('SELECT mime,data FROM docs WHERE record=? AND seq=?',(ref,seq)).fetchone()
    if not d:
        abort(404)
    ext={'application/pdf':'pdf','image/jpeg':'jpg','image/png':'png'}[d['mime']]
    return send_file(BytesIO(cipher.decrypt(d['data'])),mimetype=d['mime'],as_attachment=True,download_name=f'{ref}-{seq+1}.{ext}')
