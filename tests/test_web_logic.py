import io
from pathlib import Path
import pandas as pd

from app.web_logic import (
    authenticate,
    make_job_id,
    process_upload,
    load_plan,
    save_edited_plan,
    create_submit_package,
    load_doc2us_indication_options,
    render_indication_select,
)

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


def _sample_job(tmp_path):
    with open(SAMPLE, 'rb') as f:
        data = f.read()
    return process_upload(
        file_bytes=data,
        original_filename='raw.xlsx',
        pharmacist_name='Johnny Chew Seng Wen',
        reg_no='018161',
        apply_date='2026-06-01',
        jobs_dir=tmp_path,
    )


def test_process_upload_generates_ready_review_omit(tmp_path):
    job = _sample_job(tmp_path)
    assert Path(job['output_path']).exists()
    counts = job['counts']
    assert counts['READY'] == 7
    assert counts['REVIEW'] == 1
    assert counts['OMIT'] == 1
    df = pd.read_excel(job['output_path'], sheet_name='EPS_PLAN')
    assert 'ZOCOL' in df[df.status == 'OMIT'].iloc[0].item_name
    assert df[df.patient_name.str.contains('LU SIEW', na=False)].iloc[0].status == 'REVIEW'
    statin = df[df.item_name.str.contains('ROSUVASTATIN', case=False, na=False)].iloc[0]
    assert statin.active_ingredients == 'ROSUVASTATIN'
    assert statin.doc2us_icd_code == '5C80.0Z'
    assert statin.doc2us_indication == 'Hypercholesterolaemia, unspecified'


def test_doc2us_default_indications_are_loaded_from_harvested_dropdown():
    options = load_doc2us_indication_options()
    assert ('BA00.Z', 'Essential hypertension, unspecified') in options
    assert ('5C80.0Z', 'Hypercholesterolaemia, unspecified') in options


def test_indication_select_preserves_ai_prereview_choice_and_allows_dropdown_change():
    html = render_indication_select(3, 'BA00.Z', 'Essential hypertension, unspecified')
    assert 'name="row_3_doc2us_icd_code"' in html
    assert 'BA00.Z - Essential hypertension, unspecified' in html
    assert 'selected' in html
    assert '5C80.0Z - Hypercholesterolaemia, unspecified' in html


def test_save_edited_plan_updates_review_row_and_rebuilds_workbook(tmp_path):
    job = _sample_job(tmp_path)
    df = load_plan(tmp_path, job['job_id'])
    idx = int(df[df.patient_name.str.contains('LU SIEW', na=False)].index[0])
    saved = save_edited_plan(tmp_path, job['job_id'], {
        str(idx): {
            'status': 'READY',
            'skip_reason': '',
            'indication': 'Hypertension',
            'frequency': 'Once daily',
            'duration_days': '30',
            'prescribed_amount': '30',
        }
    })
    assert saved['counts']['READY'] == 8
    edited = load_plan(tmp_path, job['job_id'])
    assert edited.loc[idx, 'status'] == 'READY'
    assert edited.loc[idx, 'prescribed_amount'] == 30


def test_create_submit_package_contains_ready_rows_only(tmp_path):
    job = _sample_job(tmp_path)
    package = create_submit_package(tmp_path, job['job_id'])
    assert Path(package['queue_path']).exists()
    q = pd.read_excel(package['queue_path'])
    assert set(q['status']) == {'READY'}
    assert len(q) == job['counts']['READY']
