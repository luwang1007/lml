import csv
import io
import os

import pandas as pd
import pytest

from config import COL_DATE, COL_FAMILY, COL_ONPROMO, COL_SALES, COL_STORE


def _build_valid_rows(days=100):
    rows = []
    for day in range(days):
        date = (pd.Timestamp('2020-01-01') + pd.Timedelta(days=day)).date()
        for family in ['BEVERAGES', 'PRODUCE']:
            rows.append({
                COL_DATE: date.isoformat(),
                COL_STORE: 1,
                COL_FAMILY: family,
                COL_SALES: float(100 + day + (10 if family == 'PRODUCE' else 0)),
                COL_ONPROMO: 0,
            })
    return rows


@pytest.fixture(scope='session', autouse=True)
def create_test_data_files():
    test_data_dir = os.path.join(os.path.dirname(__file__), 'test_data')
    os.makedirs(test_data_dir, exist_ok=True)

    valid_rows = _build_valid_rows(days=100)
    pd.DataFrame(valid_rows).to_csv(os.path.join(test_data_dir, 'valid_utf8.csv'), index=False, encoding='utf-8')

    missing_column_rows = [
        {COL_DATE: row[COL_DATE], COL_STORE: row[COL_STORE], COL_FAMILY: row[COL_FAMILY], COL_ONPROMO: row[COL_ONPROMO]}
        for row in valid_rows
    ]
    pd.DataFrame(missing_column_rows).to_csv(os.path.join(test_data_dir, 'missing_column.csv'), index=False, encoding='utf-8')

    negative_rows = []
    for idx, row in enumerate(valid_rows):
        item = dict(row)
        if idx % 15 == 0:
            item[COL_SALES] = -5.0
        if idx % 12 == 0:
            item[COL_ONPROMO] = -2
        negative_rows.append(item)
    pd.DataFrame(negative_rows).to_csv(os.path.join(test_data_dir, 'negative_values.csv'), index=False, encoding='utf-8')

    duplicate_rows = valid_rows + [dict(valid_rows[0]), dict(valid_rows[1])]
    pd.DataFrame(duplicate_rows).to_csv(os.path.join(test_data_dir, 'duplicate_rows.csv'), index=False, encoding='utf-8')

    null_sales_rows = []
    for idx, row in enumerate(valid_rows):
        item = dict(row)
        if idx % 20 == 0:
            item[COL_SALES] = None
        null_sales_rows.append(item)
    pd.DataFrame(null_sales_rows).to_csv(os.path.join(test_data_dir, 'null_sales.csv'), index=False, encoding='utf-8')

    return test_data_dir


@pytest.fixture
def app_client():
    from app import app

    app.config['TESTING'] = True
    app.config['SECRET_KEY'] = 'test-key'
    with app.test_client() as client:
        yield client


@pytest.fixture
def valid_csv_bytes():
    rows = _build_valid_rows(days=100)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=[COL_DATE, COL_STORE, COL_FAMILY, COL_SALES, COL_ONPROMO])
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue().encode('utf-8')


@pytest.fixture
def uploaded_session(app_client, valid_csv_bytes):
    data = {'file': (io.BytesIO(valid_csv_bytes), 'test.csv')}
    resp = app_client.post('/api/upload', data=data, content_type='multipart/form-data')
    assert resp.json['code'] == 200, f"Upload failed: {resp.json}"
    return resp.json['data']['session_id']
