from __future__ import annotations

import os
import shutil
import uuid
import csv
from html import escape
from pathlib import Path
from typing import Dict, Any

import pandas as pd

from . import eps_bulk_core

EDITABLE_COLUMNS = [
    'status', 'skip_reason', 'patient_name', 'patient_ic', 'mobile', 'email', 'item_name', 'indication',
    'diagnosis_search', 'doc2us_icd_code', 'doc2us_indication', 'route', 'dose', 'dose_unit', 'frequency', 'duration_days', 'prescribed_amount',
    'prescribed_unit', 'drug_remark', 'questionnaire_mode', 'bp', 'hr', 'glucose', 'last_appointment_date',
    'next_appointment_date', 'follow_up_under', 'referred_by', 'pharmacist_reg_no', 'screening_remarks'
]
NUMERIC_COLUMNS = {'qty', 'duration_days', 'prescribed_amount'}


def load_doc2us_indication_options() -> list[tuple[str, str]]:
    """Doc2Us default EPS indication dropdown options harvested from /Api/Icd/GetDefaultIcdsForEPS.

    Kept as a local controlled list so the app can work offline and pharmacists can review the AI-preselected choice.
    """
    path = Path(__file__).resolve().parents[1] / 'data' / 'doc2us_default_indications.csv'
    with open(path, newline='', encoding='utf-8-sig') as f:
        return [(r['icd_code'], r['icd_description']) for r in csv.DictReader(f)]


def render_indication_select(row_idx: int, selected_code: str, selected_text: str = '') -> str:
    selected_code = str(selected_code or '').strip()
    selected_text = str(selected_text or '').strip()
    options = ['<option value="">-- pharmacist choose Doc2Us indication --</option>']
    found = False
    for code, desc in load_doc2us_indication_options():
        is_selected = code == selected_code or (not selected_code and desc == selected_text)
        if is_selected:
            found = True
        selected_attr = 'selected' if is_selected else ''
        options.append(
            f'<option value="{escape(code)}" data-desc="{escape(desc)}" {selected_attr}>'
            f'{escape(code)} - {escape(desc)}</option>'
        )
    if selected_code and not found:
        options.insert(1, f'<option value="{escape(selected_code)}" data-desc="{escape(selected_text)}" selected>{escape(selected_code)} - {escape(selected_text)}</option>')
    hidden = f'<input type="hidden" name="row_{row_idx}_doc2us_indication" value="{escape(selected_text)}">'
    html_options = ''.join(options)
    return f'<select name="row_{row_idx}_doc2us_icd_code">{html_options}</select>{hidden}'


def _allowed_logins() -> dict[str, str]:
    """Pilot shared-app login list.

    Default enables the first approved Doc2Us/EPS account. On deployment, set
    EPS_ALLOWED_EMAIL and EPS_ALLOWED_PASSWORD environment variables so the
    password is not hardcoded in platform configuration/history.
    """
    email = os.environ.get('EPS_ALLOWED_EMAIL', 'qsbjc1@alpropharmacy.com').strip().lower()
    password = os.environ.get('EPS_ALLOWED_PASSWORD', 'Alpro-123')
    return {email: password}


def authenticate(email: str, password: str) -> bool:
    """Temporary shared-app login: accept only the approved EPS pilot account."""
    return _allowed_logins().get((email or '').strip().lower()) == (password or '')


def make_job_id() -> str:
    return uuid.uuid4().hex


def _safe_job_dir(jobs_dir: str | Path, job_id: str) -> Path:
    if not job_id or not str(job_id).isalnum():
        raise ValueError('Invalid job id')
    job_dir = Path(jobs_dir) / job_id
    if not job_dir.exists():
        raise FileNotFoundError('Job not found')
    return job_dir


def _plan_path(job_dir: Path) -> Path:
    files = list(job_dir.glob('*_EPS_PLAN.xlsx'))
    if not files:
        raise FileNotFoundError('Plan workbook not found')
    return files[0]


def _write_plan_workbook(plan: pd.DataFrame, output_path: Path) -> None:
    with pd.ExcelWriter(output_path, engine='openpyxl') as w:
        plan.to_excel(w, index=False, sheet_name='EPS_PLAN')
        plan.groupby(['status', 'medication_class'], dropna=False).size().reset_index(name='count').to_excel(
            w, index=False, sheet_name='SUMMARY'
        )


def _job_summary(job_id: str, output_path: Path, plan: pd.DataFrame) -> Dict[str, Any]:
    counts = {str(k): int(v) for k, v in plan['status'].value_counts(dropna=False).to_dict().items()}
    preview_cols = ['status','skip_reason','patient_name','patient_ic','item_name','qty','medication_class','indication','frequency','duration_days','prescribed_amount','next_appointment_date']
    preview = plan[[c for c in preview_cols if c in plan.columns]].fillna('').to_dict(orient='records')
    return {
        'job_id': job_id,
        'output_path': str(output_path),
        'download_name': output_path.name,
        'counts': counts,
        'preview': preview,
    }


def load_plan(jobs_dir: str | Path, job_id: str) -> pd.DataFrame:
    job_dir = _safe_job_dir(jobs_dir, job_id)
    return pd.read_excel(_plan_path(job_dir), sheet_name='EPS_PLAN')


def process_upload(
    file_bytes: bytes,
    original_filename: str,
    pharmacist_name: str,
    reg_no: str,
    apply_date: str,
    jobs_dir: str | Path,
) -> Dict[str, Any]:
    jobs_dir = Path(jobs_dir)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    job_id = make_job_id()
    job_dir = jobs_dir / job_id
    job_dir.mkdir()
    safe_name = Path(original_filename or 'upload.xlsx').name
    input_path = job_dir / safe_name
    input_path.write_bytes(file_bytes)

    # The core module expects its medication_rules.csv beside itself. Use shared web data rules.
    web_rules = Path(__file__).resolve().parents[1] / 'data' / 'medication_rules.csv'
    core_rules = Path(eps_bulk_core.__file__).resolve().parent / 'medication_rules.csv'
    if web_rules.exists() and not core_rules.exists():
        shutil.copy2(web_rules, core_rules)

    plan = eps_bulk_core.make_plan(str(input_path), pharmacist_name, reg_no, pd.to_datetime(apply_date).date())
    output_path = job_dir / f'{input_path.stem}_EPS_PLAN.xlsx'
    _write_plan_workbook(plan, output_path)
    summary = _job_summary(job_id, output_path, plan)
    summary['input_path'] = str(input_path)
    return summary


def save_edited_plan(jobs_dir: str | Path, job_id: str, edits: dict[str, dict[str, str]]) -> Dict[str, Any]:
    job_dir = _safe_job_dir(jobs_dir, job_id)
    output_path = _plan_path(job_dir)
    plan = pd.read_excel(output_path, sheet_name='EPS_PLAN')
    for row_key, values in edits.items():
        if not str(row_key).isdigit():
            continue
        idx = int(row_key)
        if idx not in plan.index:
            continue
        for col in EDITABLE_COLUMNS:
            if col not in values or col not in plan.columns:
                continue
            val = values[col]
            if col == 'status':
                val = str(val or '').strip().upper()
                if val not in {'READY', 'REVIEW', 'OMIT'}:
                    val = 'REVIEW'
            elif col in NUMERIC_COLUMNS:
                try:
                    val = int(float(val)) if str(val).strip() != '' else 0
                except ValueError:
                    val = 0
            else:
                val = str(val or '').strip()
            plan.at[idx, col] = val
    _write_plan_workbook(plan, output_path)
    return _job_summary(job_id, output_path, plan)


def create_submit_package(jobs_dir: str | Path, job_id: str) -> Dict[str, Any]:
    job_dir = _safe_job_dir(jobs_dir, job_id)
    output_path = _plan_path(job_dir)
    plan = pd.read_excel(output_path, sheet_name='EPS_PLAN')
    ready = plan[plan['status'].astype(str).str.upper() == 'READY'].copy()
    queue_path = job_dir / f'{output_path.stem}_DOC2US_READY_QUEUE.xlsx'
    with pd.ExcelWriter(queue_path, engine='openpyxl') as w:
        ready.to_excel(w, index=False, sheet_name='READY_TO_SUBMIT')
    return {'job_id': job_id, 'queue_path': str(queue_path), 'count': int(len(ready))}
