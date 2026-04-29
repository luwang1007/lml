import logging
import warnings

import joblib
import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.stattools import adfuller

from config import (
    ARIMA_P_RANGE, ARIMA_Q_RANGE, ARIMA_CRITERION,
    MODEL_DIR, safe_family_name,
)
import os

logger = logging.getLogger(__name__)


class ARIMAModel:
    def __init__(self, config: dict = None):
        cfg = config or {}
        self.p_range   = cfg.get('p_range',   ARIMA_P_RANGE)
        self.q_range   = cfg.get('q_range',   ARIMA_Q_RANGE)
        self.criterion = cfg.get('criterion', ARIMA_CRITERION)

        self.order        = None
        self.aic          = None
        self.bic          = None
        self.model_result = None
        self.train_series = None
        self.fitted_values = None
        self._order_cache  = {}

    def auto_select_order(self, series: pd.Series) -> tuple:
        series_hash = hash(series.values.tobytes())
        if series_hash in self._order_cache:
            return self._order_cache[series_hash]

        d = self._determine_d(series)
        candidates = []
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            for p in self.p_range:
                for q in self.q_range:
                    try:
                        res = ARIMA(series, order=(p, d, q)).fit()
                        score = res.aic if self.criterion == 'aic' else res.bic
                        candidates.append((p, d, q, score))
                    except Exception:
                        continue

        if candidates:
            best = min(candidates, key=lambda x: x[3])
            order = (best[0], best[1], best[2])
        else:
            logger.warning('ARIMA 全参数组合失败，使用 fallback ARIMA(1,1,1)')
            order = (1, 1, 1)

        self._order_cache[series_hash] = order
        return order

    def _determine_d(self, series: pd.Series) -> int:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                p = adfuller(series.dropna())[1]
                if p < 0.05:
                    return 0
                p1 = adfuller(series.diff().dropna())[1]
                return 1 if p1 < 0.05 else 2
        except Exception:
            return 1

    def fit(self, train_series: pd.Series, order: tuple = None):
        self.train_series = train_series
        self.order = order or self.auto_select_order(train_series)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            self.model_result = ARIMA(train_series, order=self.order).fit()
        self.aic = float(self.model_result.aic)
        self.bic = float(self.model_result.bic)
        self.fitted_values = pd.Series(
            np.clip(self.model_result.fittedvalues.values, 0, None),
            index=train_series.index,
        )

    def predict(self, steps: int = 30) -> dict:
        fc   = self.model_result.get_forecast(steps=steps)
        mean = fc.predicted_mean
        ci   = fc.conf_int(alpha=0.05)

        last_date = self.train_series.index[-1]
        dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=steps)

        return {
            'dates':    [d.strftime('%Y-%m-%d') for d in dates],
            'forecast': [max(0.0, float(v)) for v in mean],
            'lower_ci': [max(0.0, float(v)) for v in ci.iloc[:, 0]],
            'upper_ci': [max(0.0, float(v)) for v in ci.iloc[:, 1]],
            'order':    list(self.order),
            'aic':      float(self.aic),
            'bic':      float(self.bic),
        }

    def get_fitted_vs_actual(self) -> dict:
        return {
            'dates':  [d.strftime('%Y-%m-%d') for d in self.train_series.index],
            'actual': [max(0.0, float(v)) for v in self.train_series.values],
            'fitted': [max(0.0, float(v)) for v in self.fitted_values.values],
        }

    def evaluate(self, test_series: pd.Series) -> dict:
        from modules.evaluator import ModelEvaluator
        preds = []
        history = list(self.train_series.values)
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            for actual_val in test_series.values:
                try:
                    model = ARIMA(history, order=self.order).fit()
                    pred = float(model.forecast(steps=1).iloc[0])
                except Exception:
                    pred = float(np.mean(history[-7:]))
                preds.append(max(0.0, pred))
                history.append(float(actual_val))

        metrics = ModelEvaluator.compute_all(
            np.array(test_series.values, dtype=float),
            np.array(preds, dtype=float),
            model_name='ARIMA',
        )
        metrics['predictions'] = [float(v) for v in preds]
        metrics['dates'] = [d.strftime('%Y-%m-%d') for d in test_series.index]
        return metrics

    def save(self, filepath: str):
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        joblib.dump(self, filepath)

    @classmethod
    def load(cls, filepath: str):
        return joblib.load(filepath)

    @staticmethod
    def model_path(family: str, store_nbr: int) -> str:
        fname = f'arima_{safe_family_name(family)}_{store_nbr}.pkl'
        return os.path.join(MODEL_DIR, fname)
