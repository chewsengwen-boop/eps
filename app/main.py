from __future__ import annotations

from datetime import date
from pathlib import Path
from html import escape

from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse

from .web_logic import authenticate, process_upload, load_plan, save_edited_plan, create_submit_package, EDITABLE_COLUMNS

BASE = Path(__file__).resolve().parents[1]
JOBS_DIR = BASE / 'jobs'

app = FastAPI(title='EPS Shared Automation', version='0.2.0')

CSS = """
body{font-family:Arial,sans-serif;background:#f6f8fb;color:#1f2937;margin:0;padding:32px}.card{max-width:520px;margin:40px auto;background:white;padding:28px;border-radius:14px;box-shadow:0 8px 30px #0001}.wide{max-width:1400px;margin:20px auto;background:white;padding:24px;border-radius:14px;box-shadow:0 8px 30px #0001}label{display:block;margin:14px 0;font-weight:600}input,select,textarea{box-sizing:border-box;display:block;width:100%;padding:9px;margin-top:6px;border:1px solid #cbd5e1;border-radius:8px}textarea{min-width:180px;min-height:42px}button,.button{background:#0f766e;color:white;border:0;border-radius:8px;padding:11px 16px;text-decoration:none;display:inline-block;font-weight:700;cursor:pointer}.secondary{background:#475569}.danger{background:#b91c1c}.err{background:#fee2e2;color:#991b1b;padding:10px;border-radius:8px}.note{background:#eef6ff;padding:12px;border-radius:8px;margin-top:18px}.summary{margin:14px 0;line-height:2.5}.pill{padding:8px 12px;border-radius:999px;margin-right:10px;font-weight:700}.READY{background:#dcfce7}.REVIEW{background:#fef3c7}.OMIT{background:#fee2e2}table{border-collapse:collapse;width:100%;font-size:13px}th,td{border:1px solid #e5e7eb;padding:7px;vertical-align:top}th{background:#f1f5f9;text-align:left;position:sticky;top:0}.grid{overflow:auto;max-height:72vh}.rowactions{display:flex;gap:10px;flex-wrap:wrap;margin:16px 0}.small{font-size:12px;color:#64748b}
"""


def html_page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{escape(title)}</title><style>{CSS}</style></head><body>{body}</body></html>')


def require_login(request: Request):
    email = request.cookies.get('eps_email')
    if not email:
        return None
    return email


def render_review(job_id: str, request: Request, notice: str = '') -> HTMLResponse:
    email = require_login(request)
    if not email:
        return RedirectResponse('/', status_code=303)
    df = load_plan(JOBS_DIR, job_id).fillna('')
    counts = df['status'].value_counts(dropna=False).to_dict()
    pills = ''.join(f'<span class="pill {escape(str(k))}">{escape(str(k))}: {int(v)}</span>' for k, v in counts.items())
    msg = f'<div class="note">{escape(notice)}</div>' if notice else ''
    rows = []
    for idx, r in df.iterrows():
        status = escape(str(r.get('status', '')))
        status_select = '<select name="row_{0}_status"><option {1}>READY</option><option {2}>REVIEW</option><option {3}>OMIT</option></select>'.format(
            idx,
            'selected' if status == 'READY' else '',
            'selected' if status == 'REVIEW' else '',
            'selected' if status == 'OMIT' else '',
        )
        rows.append(f'''<tr class="{status}">
<td>{idx}<br>{status_select}</td>
<td><textarea name="row_{idx}_skip_reason">{escape(str(r.get('skip_reason','')))}</textarea></td>
<td><input name="row_{idx}_patient_name" value="{escape(str(r.get('patient_name','')))}"><span class="small">IC</span><input name="row_{idx}_patient_ic" value="{escape(str(r.get('patient_ic','')))}"><span class="small">Mobile</span><input name="row_{idx}_mobile" value="{escape(str(r.get('mobile','')))}"><span class="small">Email</span><input name="row_{idx}_email" value="{escape(str(r.get('email','')))}"></td>
<td>{escape(str(r.get('item_name','')))}<br><span class="small">Qty: {escape(str(r.get('qty','')))} | Class: {escape(str(r.get('medication_class','')))}</span></td>
<td><input name="row_{idx}_indication" value="{escape(str(r.get('indication','')))}"><span class="small">Diagnosis search</span><input name="row_{idx}_diagnosis_search" value="{escape(str(r.get('diagnosis_search','')))}"></td>
<td><span class="small">Route</span><input name="row_{idx}_route" value="{escape(str(r.get('route','')))}"><span class="small">Dose</span><input name="row_{idx}_dose" value="{escape(str(r.get('dose','')))}"><span class="small">Unit</span><input name="row_{idx}_dose_unit" value="{escape(str(r.get('dose_unit','')))}"><span class="small">Frequency</span><input name="row_{idx}_frequency" value="{escape(str(r.get('frequency','')))}"></td>
<td><span class="small">Days</span><input name="row_{idx}_duration_days" value="{escape(str(r.get('duration_days','')))}"><span class="small">Amount</span><input name="row_{idx}_prescribed_amount" value="{escape(str(r.get('prescribed_amount','')))}"><span class="small">Unit</span><input name="row_{idx}_prescribed_unit" value="{escape(str(r.get('prescribed_unit','')))}"></td>
<td><span class="small">BP</span><input name="row_{idx}_bp" value="{escape(str(r.get('bp','')))}"><span class="small">HR</span><input name="row_{idx}_hr" value="{escape(str(r.get('hr','')))}"><span class="small">Glucose</span><input name="row_{idx}_glucose" value="{escape(str(r.get('glucose','')))}"><span class="small">Next appt</span><input name="row_{idx}_next_appointment_date" value="{escape(str(r.get('next_appointment_date','')))}"></td>
<td><textarea name="row_{idx}_drug_remark">{escape(str(r.get('drug_remark','')))}</textarea><span class="small">Screening remarks</span><textarea name="row_{idx}_screening_remarks">{escape(str(r.get('screening_remarks','')))}</textarea></td>
</tr>''')
    body = f'''<main class="wide">
<h1>EPS Plan Review + Edit</h1>
<p>Logged in as {escape(email)}</p>{msg}
<div class="summary">{pills}</div>
<div class="rowactions">
<a class="button secondary" href="/upload">Upload another file</a>
<a class="button" href="/download/{escape(job_id)}">Download current Excel</a>
<form method="post" action="/submit/{escape(job_id)}" style="display:inline"><button type="submit" class="danger">Prepare Doc2Us Submit Queue</button></form>
</div>
<form method="post" action="/save/{escape(job_id)}">
<p class="note"><b>Editable now:</b> status, patient info, indication, dose, frequency, days, amount, BP/HR/glucose, remarks. Change REVIEW to READY only after pharmacist confirms the medication details are correct.</p>
<div class="grid"><table><thead><tr><th># / Status</th><th>Reason</th><th>Patient</th><th>Medication</th><th>Indication</th><th>Dose/Frequency</th><th>Duration/Amount</th><th>Screening</th><th>Remarks</th></tr></thead><tbody>{''.join(rows)}</tbody></table></div>
<p><button type="submit">Save Edits + Rebuild Excel</button></p>
</form>
<p class="note"><b>Submit queue:</b> This creates a READY-only queue for Doc2Us submission after final review. The live website submission button is separated so accidental upload does not submit prescriptions.</p>
</main>'''
    return html_page('Review EPS Plan', body)


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
    email = require_login(request)
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
    if not require_login(request):
        return RedirectResponse('/', status_code=303)
    if not excel_file.filename or not excel_file.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(400, 'Please upload an Excel file')
    data = await excel_file.read()
    job = process_upload(data, excel_file.filename, pharmacist_name, reg_no, apply_date, JOBS_DIR)
    return RedirectResponse(f'/review/{job["job_id"]}', status_code=303)


@app.get('/review/{job_id}', response_class=HTMLResponse)
def review(job_id: str, request: Request):
    return render_review(job_id, request)


@app.post('/save/{job_id}', response_class=HTMLResponse)
async def save(job_id: str, request: Request):
    if not require_login(request):
        return RedirectResponse('/', status_code=303)
    form = await request.form()
    edits: dict[str, dict[str, str]] = {}
    prefix = 'row_'
    for key, val in form.items():
        if not key.startswith(prefix):
            continue
        rest = key[len(prefix):]
        row_id, _, col = rest.partition('_')
        if not row_id.isdigit() or col not in EDITABLE_COLUMNS:
            continue
        edits.setdefault(row_id, {})[col] = str(val)
    save_edited_plan(JOBS_DIR, job_id, edits)
    return render_review(job_id, request, 'Saved edits and rebuilt the downloadable Excel workbook.')


@app.post('/submit/{job_id}', response_class=HTMLResponse)
def submit_queue(job_id: str, request: Request):
    if not require_login(request):
        return RedirectResponse('/', status_code=303)
    package = create_submit_package(JOBS_DIR, job_id)
    body = f'''<main class="card wide">
<h1>Doc2Us Submit Queue Prepared</h1>
<p>{package['count']} READY rows are included. REVIEW and OMIT rows are excluded.</p>
<p><a class="button" href="/download-submit/{escape(job_id)}">Download READY Submit Queue</a> <a class="button secondary" href="/review/{escape(job_id)}">Back to review</a></p>
<div class="note"><b>Important:</b> The website now gives you a submit queue option, but full one-click live Doc2Us submission still needs final EPS selector mapping in the real EPS browser flow. I will not silently submit anything without pharmacist confirmation. Next build step is to connect this queue to the EPS browser automation and test one selected patient first.</div>
</main>'''
    return html_page('Doc2Us Submit Queue', body)


@app.get('/download-submit/{job_id}')
def download_submit(job_id: str):
    if not job_id.isalnum():
        raise HTTPException(400, 'Invalid job id')
    job_dir = JOBS_DIR / job_id
    files = list(job_dir.glob('*_DOC2US_READY_QUEUE.xlsx')) if job_dir.exists() else []
    if not files:
        create_submit_package(JOBS_DIR, job_id)
        files = list(job_dir.glob('*_DOC2US_READY_QUEUE.xlsx'))
    if not files:
        raise HTTPException(404, 'Submit queue not found')
    return FileResponse(str(files[0]), filename=files[0].name)


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
