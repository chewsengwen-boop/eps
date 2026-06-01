import io
from pathlib import Path
import pandas as pd

from app.web_logic import authenticate, make_job_id, process_upload

SAMPLE = '/mnt/c/Users/User/Downloads/OUTLET POISON B&C TRANSACTION NO_01-06-2026 (Web).xlsx'


def test_authenticate_accepts_doc2us_trial_account():
    assert authenticate('qsbjc1@alpropharmacy.com', 'Alpro-123') is True


def test_authenticate_rejects_wrong_password():
    assert authenticate('qsbjc1@alpropharmacy.com', 'wrong') is False


def test_make_job_id_is_safe_and_unique():
    a = make_job_id()
    b = make_job_id()
    assert a != b
    assert '/' not in a and '..' not in a


def test_process_upload_generates_ready_review_omit(tmp_path):
    with open(SAMPLE, 'rb') as f:
        data = f.read()
    job = process_upload(
        file_bytes=data,
        original_filename='raw.xlsx',
        pharmacist_name='Johnny Chew Seng Wen',
        reg_no='018161',
        apply_date='2026-06-01',
        jobs_dir=tmp_path,
    )
    assert Path(job['output_path']).exists()
    counts = job['counts']
    assert counts['READY'] == 7
    assert counts['REVIEW'] == 1
    assert counts['OMIT'] == 1
    df = pd.read_excel(job['output_path'], sheet_name='EPS_PLAN')
    assert 'ZOCOL' in df[df.status == 'OMIT'].iloc[0].item_name
    assert df[df.patient_name.str.contains('LU SIEW', na=False)].iloc[0].status == 'REVIEW'
