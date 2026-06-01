from __future__ import annotations

import os
from pathlib import Path
from datetime import date

from fastapi import FastAPI, Request, Form, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .web_logic import authenticate, process_upload

BASE = Path(__file__).resolve().parents[1]
JOBS_DIR = BASE / 'jobs'

app = FastAPI(title='EPS Shared Automation', version='0.1.0')
templates = Jinja2Templates(directory=str(BASE / 'app' / 'templates'))


@app.get('/', response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse('login.html', {'request': request, 'error': ''})


@app.post('/login', response_class=HTMLResponse)
def login(request: Request, email: str = Form(...), password: str = Form(...)):
    if not authenticate(email, password):
        return templates.TemplateResponse('login.html', {'request': request, 'error': 'Invalid login. For pilot, only qsbjc1@alpropharmacy.com is enabled.'}, status_code=401)
    resp = RedirectResponse('/upload', status_code=303)
    resp.set_cookie('eps_email', email, httponly=True, samesite='lax')
    return resp


@app.get('/upload', response_class=HTMLResponse)
def upload_page(request: Request):
    if not request.cookies.get('eps_email'):
        return RedirectResponse('/', status_code=303)
    return templates.TemplateResponse('upload.html', {'request': request, 'today': date.today().isoformat(), 'email': request.cookies.get('eps_email')})


@app.post('/process', response_class=HTMLResponse)
async def process_file(
    request: Request,
    pharmacist_name: str = Form(...),
    reg_no: str = Form(...),
    apply_date: str = Form(...),
    excel_file: UploadFile = File(...),
):
    if not request.cookies.get('eps_email'):
        return RedirectResponse('/', status_code=303)
    if not excel_file.filename.lower().endswith(('.xlsx', '.xls')):
        raise HTTPException(400, 'Please upload an Excel file')
    data = await excel_file.read()
    job = process_upload(data, excel_file.filename, pharmacist_name, reg_no, apply_date, JOBS_DIR)
    return templates.TemplateResponse('review.html', {'request': request, 'job': job, 'email': request.cookies.get('eps_email')})


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
