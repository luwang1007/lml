import json

import numpy as np
import pandas as pd
import pytest

from modules.arima_model import ARIMAModel
from modules.evaluator import ModelEvaluator
from modules.lstm_model import LSTMModel


def _series(n=200):
    dates = pd.date_range('2020-01-01', periods=n, freq='D')
    values = 100 + np.sin(np.arange(n) / 10.0) * 5 + np.arange(n) * 0.2
    return pd.Series(values, index=dates)


def test_arima_predict_length():
    model = ARIMAModel({'p_range': range(0, 2), 'q_range': range(0, 2)})
    model.fit(_series(200))
    result = model.predict(30)
    assert len(result['forecast']) == 30


def test_arima_predict_non_negative():
    model = ARIMAModel({'p_range': range(0, 2), 'q_range': range(0, 2)})
    model.fit(_series(200))
    result = model.predict(30)
    assert min(result['forecast']) >= 0


def test_arima_order_tuple():
    model = ARIMAModel({'p_range': range(0, 2), 'q_range': range(0, 2)})
    order = model.auto_select_order(_series(120))
    assert isinstance(order, tuple)
    assert len(order) == 3


def test_arima_save_load_roundtrip(tmp_path):
    series = _series(160)
    model = ARIMAModel({'p_range': range(0, 2), 'q_range': range(0, 2)})
    model.fit(series)
    expected = model.predict(10)['forecast']
    path = tmp_path / 'arima.pkl'
    model.save(str(path))
    loaded = ARIMAModel.load(str(path))
    actual = loaded.predict(10)['forecast']
    diff = np.max(np.abs(np.array(expected) - np.array(actual)))
    assert diff < 1e-3


def test_mae_basic():
    assert ModelEvaluator.mae([1, 2, 3], [1, 2, 3]) == 0.0


def test_mae_nonzero():
    assert ModelEvaluator.mae([3, 4, 5], [2, 4, 6]) == pytest.approx(2 / 3)


def test_mape_zero_actual():
    value = ModelEvaluator.mape([0, 100], [10, 90])
    assert np.isfinite(value)


def test_compare_models_two():
    result = ModelEvaluator.compare_models({
        'ARIMA': {'mae': 1.0, 'rmse': 1.2, 'mape': 5.0, 'smape': 5.1, 'r2': 0.9},
        'Prophet': {'mae': 2.0, 'rmse': 2.2, 'mape': 10.0, 'smape': 10.2, 'r2': 0.8},
    })
    ranks = [item['rank'] for item in result['metrics_table']]
    assert ranks == [1, 2]
    assert len(set(item['model'] for item in result['metrics_table'])) == 2


def test_compare_models_single():
    result = ModelEvaluator.compare_models({
        'ARIMA': {'mae': 1.0, 'rmse': 1.2, 'mape': 5.0, 'smape': 5.1, 'r2': 0.9},
    })
    assert result['metrics_table'][0]['rank'] == 1


def test_radar_in_range():
    result = ModelEvaluator.compare_models({
        'ARIMA': {'mae': 1.0, 'rmse': 1.2, 'mape': 5.0, 'smape': 5.1, 'r2': 0.9},
        'Prophet': {'mae': 2.0, 'rmse': 2.2, 'mape': 10.0, 'smape': 10.2, 'r2': 0.8},
    })
    for series in result['radar_chart']['series']:
        assert all(0.0 <= value <= 1.0 for value in series['values'])


def test_json_serializable():
    result = ModelEvaluator.compare_models({
        'ARIMA': {'mae': 1.0, 'rmse': 1.2, 'mape': 5.0, 'smape': 5.1, 'r2': 0.9},
        'Prophet': {'mae': 2.0, 'rmse': 2.2, 'mape': 10.0, 'smape': 10.2, 'r2': 0.8},
    })
    json.dumps(result, ensure_ascii=False)


def test_lstm_sequence_shape():
    model = LSTMModel()
    X, y = model._create_sequences(np.arange(100, dtype=float), 30)
    assert X.shape == (70, 30, 1)
    assert y.shape == (70,)


def test_lstm_forward_shape():
    torch = pytest.importorskip('torch')
    from modules.lstm_model import LSTMNet

    net = LSTMNet()
    out = net(torch.randn(8, 30, 1))
    assert tuple(out.shape) == (8, 1)
