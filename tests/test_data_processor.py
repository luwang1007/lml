import os

import pandas as pd

from config import COL_DATE, COL_FAMILY, COL_ONPROMO, COL_SALES, COL_STORE
from modules.data_processor import DataProcessor


def _path(name):
    return os.path.join(os.path.dirname(__file__), 'test_data', name)


def test_load_utf8_csv():
    df = DataProcessor(_path('valid_utf8.csv')).load()
    for col in [COL_DATE, COL_STORE, COL_FAMILY, COL_SALES]:
        assert col in df.columns


def test_load_xlsx(tmp_path):
    xlsx_path = tmp_path / 'valid.xlsx'
    pd.read_csv(_path('valid_utf8.csv')).to_excel(xlsx_path, index=False)
    df = DataProcessor(str(xlsx_path)).load()
    assert not df.empty


def test_validate_missing_sales_col():
    processor = DataProcessor(_path('missing_column.csv'))
    processor.load()
    result = processor.validate()
    assert result['valid'] is False
    assert 'sales' in ' '.join(result['errors']).lower()


def test_clean_no_negative():
    processor = DataProcessor(_path('negative_values.csv'))
    processor.load()
    df = processor.clean()
    assert int((df[COL_SALES] < 0).sum()) == 0


def test_clean_no_null_sales():
    processor = DataProcessor(_path('null_sales.csv'))
    processor.load()
    df = processor.clean()
    assert int(df[COL_SALES].isna().sum()) == 0


def test_clean_duplicate_rows():
    processor = DataProcessor(_path('duplicate_rows.csv'))
    processor.load()
    df = processor.clean()
    duplicated = df.duplicated(subset=[COL_DATE, COL_FAMILY, COL_STORE]).sum()
    assert int(duplicated) == 0


def test_split_order():
    series = pd.Series(range(100), index=pd.date_range('2020-01-01', periods=100, freq='D'))
    train, val, test = DataProcessor(_path('valid_utf8.csv')).split_timeseries(series)
    assert train.index.max() < val.index.min() < test.index.min()


def test_normalize_no_leakage():
    processor = DataProcessor(_path('valid_utf8.csv'))
    train = pd.Series([1.0, 2.0, 3.0], index=pd.date_range('2020-01-01', periods=3))
    val = pd.Series([4.0, 5.0], index=pd.date_range('2020-01-04', periods=2))
    test = pd.Series([6.0], index=pd.date_range('2020-01-06', periods=1))
    train_s, val_s, test_s, scaler = processor.normalize(train, val, test)
    assert scaler.data_min_[0] == 1.0
    assert scaler.data_max_[0] == 3.0
    assert list(train_s) == [0.0, 0.5, 1.0]
    assert val_s.max() > 1.0
    assert test_s[0] > 1.0


def test_save_load_roundtrip(tmp_path):
    processor = DataProcessor(_path('valid_utf8.csv'), session_id='roundtrip_test')
    df = processor.load()
    df = processor.clean()
    agg = processor.aggregate(df)
    meta_path = processor.save_processed(df, agg)
    loaded = DataProcessor.load_processed(meta_path)
    assert loaded.shape == df.shape


def test_process_returns_meta_path():
    processor = DataProcessor(_path('valid_utf8.csv'), session_id='process_test')
    meta_path, validation = processor.process()
    assert os.path.exists(meta_path)
    assert validation['valid'] is True


def test_load_xls_rejected(tmp_path):
    xls_path = tmp_path / 'bad.xls'
    xls_path.write_bytes(b'fake-xls-content')
    processor = DataProcessor(str(xls_path))
    try:
        processor.load()
    except ValueError as exc:
        assert 'xlsx' in str(exc).lower()
    else:
        raise AssertionError('Expected ValueError for .xls file')


def test_onpromotion_non_negative():
    processor = DataProcessor(_path('negative_values.csv'))
    processor.load()
    df = processor.clean()
    assert int((df[COL_ONPROMO] < 0).sum()) == 0
