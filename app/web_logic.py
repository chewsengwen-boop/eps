from __future__ import annotations

import os
import shutil
import uuid
from pathlib import Path
from typing import Dict, Any

import pandas as pd

from . import eps_bulk_core

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
    with pd.ExcelWriter(output_path, engine='openpyxl') as w:
        plan.to_excel(w, index=False, sheet_name='EPS_PLAN')
        plan.groupby(['status','medication_class'], dropna=False).size().reset_index(name='count').to_excel(w, index=False, sheet_name='SUMMARY')
    counts = {str(k): int(v) for k, v in plan['status'].value_counts(dropna=False).to_dict().items()}
    preview_cols = ['status','skip_reason','patient_name','patient_ic','item_name','qty','medication_class','indication','frequency','duration_days','prescribed_amount','next_appointment_date']
    preview = plan[preview_cols].fillna('').to_dict(orient='records')
    return {
        'job_id': job_id,
        'input_path': str(input_path),
        'output_path': str(output_path),
        'download_name': output_path.name,
        'counts': counts,
        'preview': preview,
    }
