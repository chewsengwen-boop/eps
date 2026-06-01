from __future__ import annotations

from datetime import date
from pathlib import Path
from html import escape

from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse

from .web_logic import authenticate, process_upload

BASE = Path(__file__).resolve().parents[1]
JOBS_DIR = BASE / 'jobs'

app = FastAPI(title='EPS Shared Automation', version='0.1.1')

CSS = """
body{font-family:Arial,sans-serif;background:#f6f8fb;color:#1f2937;margin:0;padding:32px}.card{max-width:520px;margin:40px auto;background:white;padding:28px;border-radius:14px;box-shadow:0 8px 30px #0001}.wide{max-width:1200px;margin:20px auto;background:white;padding:24px;border-radius:14px;box-shadow:0 8px 30px #0001}label{display:block;margin:14px 0;font-weight:600}input{display:block;width:100%;padding:11px;margin-top:6px;border:1px solid #cbd5e1;border-radius:8px}button,.button{background:#0f766e;color:white;border:0;border-radius:8px;padding:11px 16px;text-decoration:none;display:inline-block;font-weight:700}.err{background:#fee2e2;color:#991b1b;padding:10px;border-radius:8px}.note{background:#eef6ff;padding:12px;border-radius:8px;margin-top:18px}.summary{margin:14px 0}.pill{padding:8px 12px;border-radius:999px;margin-right:10px;font-weight:700}.READY{background:#dcfce7}.REVIEW{background:#fef3c7}.OMIT{background:#fee2e2}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #e5e7eb;padding:7px;vertical-align:top}th{background:#f1f5f9;text-align:left}
"""


def html_page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f'<!doctype html><html><head><meta charset="utf-8"><title>{escape(title)}</title><style>{CSS}</style></head><body>{body}</body></html>')


@app.get('/', response_class=HTMLResponse)
def login_page(request: Request):
    error = request.query_params.get('error', '')
    err = f'<div class="err">{escape(error)}</div>' if error else ''
    body = f'''<main class="card">
<h1>EPS Shared Automation</h1>
<p>Use your Doc2Us/EPS login. Pilot account enabled first.</p>
{err}
<form method="post" action="/login">
<label>Email <input name="email" type="email" value="qsbjc1@alpropharmacy.com" required></label>
<label>Password <input name="password" type="password" required></label>
<button type="submit">Login</button>
</form>
<p class="note">This tool prepares/submits data to reduce duplicate entry. It does not prescribe; pharmacist review remains required.</p>
</main>'''
    return html_page('EPS Automation Login', body)


@app.post('/login')
def login(email: str = Form(...), password: str = Form(...)):
    if not authenticate(email, password):
        return RedirectResponse('/?error=Invalid%20login.%20Pilot%20account%20only.', status_code=303)
    resp = RedirectResponse('/upload', status_code=303)
    resp.set_cookie('eps_email', email, httponly=True, samesite='lax')
    return resp


@app.get('/upload', response_class=HTMLResponse)
def upload_page(request: Request):
    email = request.cookies.get('eps_email')
    if not email:
        return RedirectResponse('/', status_code=303)
    body = f'''<main class="card wide">
<h1>Upload Octopus Poison B/C Excel</h1>
<p>Logged in as {escape(email)}</p>
<form method="post" action="/process" enctype="multipart/form-data">
<label>Pharmacist name as per IC <input name="pharmacist_name" required placeholder="e.g. Johnny Chew Seng Wen"></label>
<label>Registration number <input name="reg_no" required placeholder="e.g. 018161"></label>
<label>Application date <input name="apply_date" type="date" value="{date.today().isoformat()}" required></label>
<label>Raw Excel file <input name="excel_file" type="file" accept=".xlsx,.xls" required></label>
<button type="submit">Generate EPS Plan</button>
</form>
<section class="note"><b>Default questionnaire:</b> BP 120/80, HR 75, Glucose 6.0, Allergy NKDA, LTM, remarks refill medication. Email defaults to IC@doc2us.com.</section>
</main>'''
    return html_page('Upload EPS Data', body)


@app.post('/process', response_class=HTMLResponse)
async def process_file(
    request: Request,
    pharmacist_name: str = Form(...),
    reg_no: str = Form(...),
    apply_date: str = Form(...),
    excel_file: UploadFile = File(...),
):
    email = request.cookies.get('eps_email')
    if not email:
        return RedirectResponse('/', status_code=303)
    if not excel_file.filename or not excel_file.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(400, 'Please upload an Excel file')
    data = await excel_file.read()
    job = process_upload(data, excel_file.filename, pharmacist_name, reg_no, apply_date, JOBS_DIR)
    pills = ''.join(f'<span class="pill {escape(str(k))}">{escape(str(k))}: {v}</span>' for k, v in job['counts'].items())
    rows = []
    for r in job['preview']:
        rows.append('<tr class="{}"><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            escape(str(r.get('status',''))), escape(str(r.get('status',''))), escape(str(r.get('skip_reason',''))),
            escape(str(r.get('patient_name',''))), escape(str(r.get('patient_ic',''))), escape(str(r.get('item_name',''))),
            escape(str(r.get('qty',''))), escape(str(r.get('medication_class',''))), escape(str(r.get('indication',''))),
            escape(str(r.get('frequency',''))), escape(str(r.get('duration_days',''))), escape(str(r.get('prescribed_amount','')))
        ))
    body = f'''<main class="wide">
<h1>EPS Plan Review</h1>
<p>Logged in as {escape(email)}</p>
<div class="summary">{pills}</div>
<p><a class="button" href="/download/{escape(job['job_id'])}">Download Excel Review Workbook</a> <a href="/upload">Upload another file</a></p>
<table><thead><tr><th>Status</th><th>Reason</th><th>Patient</th><th>IC</th><th>Item</th><th>Qty</th><th>Class</th><th>Indication</th><th>Freq</th><th>Days</th><th>Amount</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
<p class="note">READY rows can proceed after pharmacist review. REVIEW rows require checking. OMIT rows should not be submitted via EPS.</p>
</main>'''
    return html_page('Review EPS Plan', body)


@app.get('/download/{job_id}')
def download(job_id: str):
    if not job_id.isalnum():
        raise HTTPException(400, 'Invalid job id')
    job_dir = JOBS_DIR / job_id
    files = list(job_dir.glob('*_EPS_PLAN.xlsx')) if job_dir.exists() else []
    if not files:
        raise HTTPException(404, 'File not found')
    return FileResponse(str(files[0]), filename=files[0].name)


@app.get('/health')
def health():
    return {'ok': True}
