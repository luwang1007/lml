import io
import json
import time
from datetime import date
from pathlib import Path


def _upload(client, payload):
    return client.post('/api/upload', data={'file': (io.BytesIO(payload), 'test.csv')}, content_type='multipart/form-data')


def _wait_for_task(client, task_id, timeout=120):
    deadline = time.time() + timeout
    while time.time() < deadline:
        progress = client.get('/api/predict/progress', query_string={'task_id': task_id}).get_json()
        status = progress['data']['status']
        if status in {'done', 'failed', 'cancelled'}:
            return progress
        time.sleep(1)
    raise AssertionError('Prediction task did not finish in time')


def test_upload_success(app_client, valid_csv_bytes):
    resp = _upload(app_client, valid_csv_bytes)
    body = resp.get_json()
    assert body['code'] == 200
    assert 'session_id' in body['data']


def test_upload_no_file(app_client):
    resp = app_client.post('/api/upload', data={}, content_type='multipart/form-data')
    assert resp.get_json()['code'] == 400


def test_upload_xls_rejected(app_client):
    resp = app_client.post(
        '/api/upload',
        data={'file': (io.BytesIO(b'fake-xls'), 'bad.xls')},
        content_type='multipart/form-data',
    )
    body = resp.get_json()
    assert body['code'] == 400
    assert 'xlsx' in body['message'].lower()


def test_analysis_no_session(app_client):
    resp = app_client.get('/api/analysis/overview', query_string={'session_id': 'invalid'})
    assert resp.get_json()['code'] == 404


def test_analysis_overview_after_upload(app_client, uploaded_session):
    resp = app_client.get('/api/analysis/overview', query_string={'session_id': uploaded_session})
    body = resp.get_json()
    assert body['code'] == 200
    assert body['data']['total_sales'] > 0


def test_analysis_trend(app_client, uploaded_session):
    resp = app_client.get('/api/analysis/trend', query_string={
        'session_id': uploaded_session,
        'granularity': 'monthly',
        'family': 'BEVERAGES',
        'store_nbr': 1,
    })
    body = resp.get_json()
    assert body['code'] == 200
    assert 'xAxis' in body['data']
    assert 'series' in body['data']


def test_predict_empty_models(app_client, uploaded_session):
    resp = app_client.post('/api/predict/start', json={
        'session_id': uploaded_session,
        'family': 'BEVERAGES',
        'store_nbr': 1,
        'forecast_days': 7,
        'models': [],
    })
    assert resp.get_json()['code'] == 400


def test_predict_invalid_model(app_client, uploaded_session):
    resp = app_client.post('/api/predict/start', json={
        'session_id': uploaded_session,
        'family': 'BEVERAGES',
        'store_nbr': 1,
        'forecast_days': 7,
        'models': ['XGBoost'],
    })
    assert resp.get_json()['code'] == 400


def test_predict_invalid_days(app_client, uploaded_session):
    resp = app_client.post('/api/predict/start', json={
        'session_id': uploaded_session,
        'family': 'BEVERAGES',
        'store_nbr': 1,
        'forecast_days': 200,
        'models': ['ARIMA'],
    })
    assert resp.get_json()['code'] == 400


def test_predict_no_session(app_client):
    resp = app_client.post('/api/predict/start', json={
        'session_id': 'missing',
        'family': 'BEVERAGES',
        'store_nbr': 1,
        'forecast_days': 7,
        'models': ['ARIMA'],
    })
    assert resp.get_json()['code'] == 404


def test_predict_invalid_family(app_client, uploaded_session):
    resp = app_client.post('/api/predict/start', json={
        'session_id': uploaded_session,
        'family': 'FAKE_FAMILY',
        'store_nbr': 1,
        'forecast_days': 7,
        'models': ['ARIMA'],
    })
    assert resp.get_json()['code'] == 400


def test_predict_and_wait(app_client, uploaded_session):
    start = app_client.post('/api/predict/start', json={
        'session_id': uploaded_session,
        'family': 'BEVERAGES',
        'store_nbr': 1,
        'forecast_days': 7,
        'models': ['ARIMA'],
        'arima_config': {'p_range': [0, 1], 'q_range': [0, 1]},
    }).get_json()
    assert start['code'] == 200
    task_id = start['data']['task_id']

    progress = _wait_for_task(app_client, task_id)
    assert progress['data']['status'] == 'done'

    result = app_client.get('/api/predict/result', query_string={'task_id': task_id}).get_json()
    assert result['code'] == 200
    assert len(result['data']['models']['ARIMA']['forecast']) == 7
    first_forecast_date = date.fromisoformat(result['data']['models']['ARIMA']['dates'][0])
    assert first_forecast_date > date(2020, 4, 9)


def test_predict_uses_saved_model_cache(app_client, uploaded_session):
    for path in Path('data/models').glob('arima_BEVERAGES_1_*'):
        path.unlink(missing_ok=True)

    payload = {
        'session_id': uploaded_session,
        'family': 'BEVERAGES',
        'store_nbr': 1,
        'forecast_days': 7,
        'models': ['ARIMA'],
        'arima_config': {'p_range': [0, 1], 'q_range': [0, 1]},
    }

    first = app_client.post('/api/predict/start', json=payload).get_json()
    first_task_id = first['data']['task_id']
    assert _wait_for_task(app_client, first_task_id)['data']['status'] == 'done'
    first_result = app_client.get('/api/predict/result', query_string={'task_id': first_task_id}).get_json()
    assert first_result['data']['models']['ARIMA']['cache_hit'] is False

    second = app_client.post('/api/predict/start', json=payload).get_json()
    second_task_id = second['data']['task_id']
    assert _wait_for_task(app_client, second_task_id)['data']['status'] == 'done'
    second_result = app_client.get('/api/predict/result', query_string={'task_id': second_task_id}).get_json()
    assert second_result['data']['models']['ARIMA']['cache_hit'] is True

    model_path = Path('data/models')
    assert any(model_path.glob('arima_BEVERAGES_1_*.pkl'))
    assert any(model_path.glob('arima_BEVERAGES_1_*.meta.json'))


def test_predict_prophet_unavailable_rejected(app_client, uploaded_session):
    from app import PROPHET_AVAILABLE

    if PROPHET_AVAILABLE:
        return
    resp = app_client.post('/api/predict/start', json={
        'session_id': uploaded_session,
        'family': 'BEVERAGES',
        'store_nbr': 1,
        'forecast_days': 7,
        'models': ['Prophet'],
    })
    body = resp.get_json()
    assert body['code'] == 400
    assert 'Prophet 未安装' in body['message']


def test_export_forecast(app_client, uploaded_session):
    start = app_client.post('/api/predict/start', json={
        'session_id': uploaded_session,
        'family': 'BEVERAGES',
        'store_nbr': 1,
        'forecast_days': 7,
        'models': ['ARIMA'],
        'arima_config': {'p_range': [0, 1], 'q_range': [0, 1]},
    }).get_json()
    task_id = start['data']['task_id']
    progress = _wait_for_task(app_client, task_id)
    assert progress['data']['status'] == 'done'

    resp = app_client.get('/api/export/forecast', query_string={'task_id': task_id})
    assert resp.status_code == 200
    assert 'attachment' in resp.headers['Content-Disposition']


def test_predict_cancel(app_client, uploaded_session):
    start = app_client.post('/api/predict/start', json={
        'session_id': uploaded_session,
        'family': 'BEVERAGES',
        'store_nbr': 1,
        'forecast_days': 7,
        'models': ['ARIMA'],
        'arima_config': {'p_range': [0, 1], 'q_range': [0, 1]},
    }).get_json()
    task_id = start['data']['task_id']

    cancel = app_client.post('/api/predict/cancel', json={'task_id': task_id}).get_json()
    assert cancel['code'] == 200

    progress = _wait_for_task(app_client, task_id, timeout=10)
    assert progress['data']['status'] == 'cancelled'


def test_json_no_nan(app_client, uploaded_session):
    endpoints = [
        '/api/analysis/overview',
        '/api/analysis/trend?granularity=monthly',
        '/api/analysis/category_pie',
        '/api/analysis/top_families',
        '/api/analysis/correlation',
        '/api/analysis/weekday',
        '/api/analysis/promotion',
    ]
    for endpoint in endpoints:
        resp = app_client.get(endpoint)
        body = resp.get_data(as_text=True)
        assert 'NaN' not in body
        parsed = json.loads(body)
        assert parsed['code'] == 200
