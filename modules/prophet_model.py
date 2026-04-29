import os
import sys
import logging
import contextlib
from datetime import datetime

import joblib
import numpy as np
import pandas as pd

from config import DATA_RAW_DIR, MODEL_DIR as DATA_MODELS_DIR, safe_family_name


logger = logging.getLogger(__name__)


try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    logger.warning('Prophet 未安装。设置 PROPHET_ENABLED=False 可跳过此模块。')


@contextlib.contextmanager
def suppress_stdout_stderr():
    with open(os.devnull, 'w') as devnull:
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout, sys.stderr = devnull, devnull
        try:
            yield
        finally:
            sys.stdout, sys.stderr = old_stdout, old_stderr


class ProphetModel:
    def __init__(self, config=None):
        defaults = {
            'changepoint_prior_scale': 0.05,
            'seasonality_prior_scale': 10.0,
            'seasonality_mode': 'multiplicative',
            'yearly_seasonality': True,
            'weekly_seasonality': True,
            'daily_seasonality': False,
            'forecast_days': 30,
            'use_onpromotion': False,
        }
        self.config = {**defaults, **(config or {})}
        self.model = None
        self.fitted_values = None
        self.train_series = None

    def _load_holidays(self):
        holidays_path = os.path.join(DATA_RAW_DIR, 'holidays_events.csv')
        try:
            holidays_df = pd.read_csv(holidays_path)
            holidays_df = holidays_df[
                holidays_df['type'].isin(['Holiday', 'Event', 'Additional'])
            ].copy()
            transferred_mask = holidays_df['transferred'].astype(str).str.lower() == 'true'
            holidays_df = holidays_df[~transferred_mask].copy()

            window_map = {
                'Holiday': (-1, 1),
                'Event': (0, 0),
                'Additional': (0, 0),
            }
            holidays_df['ds'] = pd.to_datetime(holidays_df['date'])
            holidays_df['holiday'] = holidays_df['description'].astype(str)
            holidays_df['lower_window'] = holidays_df['type'].map(lambda x: window_map[x][0])
            holidays_df['upper_window'] = holidays_df['type'].map(lambda x: window_map[x][1])

            result = holidays_df[['ds', 'holiday', 'lower_window', 'upper_window']].dropna()
            return result if not result.empty else None
        except FileNotFoundError:
            logger.warning('未找到 holidays_events.csv，Prophet 将在无节假日特征下运行。')
            return None
        except Exception as exc:
            logger.warning('加载 holidays_events.csv 失败，将忽略节假日特征: %s', exc)
            return None

    def _prepare_dataframe(self, series, onpromotion_series=None):
        df = pd.DataFrame({
            'ds': pd.to_datetime(series.index.to_series().reset_index(drop=True)),
            'y': pd.Series(series.values).reset_index(drop=True),
        })

        if self.config.get('seasonality_mode') == 'multiplicative':
            df.loc[df['y'] == 0, 'y'] = 0.01

        if self.config.get('use_onpromotion') and onpromotion_series is not None:
            aligned_onpromotion = onpromotion_series.reindex(series.index).fillna(0)
            df['onpromotion'] = pd.Series(aligned_onpromotion.values).reset_index(drop=True)

        return df

    def fit(self, train_series, onpromotion_series=None):
        if not PROPHET_AVAILABLE:
            raise ImportError('Prophet 未安装，请按 README 安装说明处理，或在 config.py 设置 PROPHET_ENABLED=False')

        holidays_df = self._load_holidays()
        prophet_kwargs = {
            'changepoint_prior_scale': self.config['changepoint_prior_scale'],
            'seasonality_prior_scale': self.config['seasonality_prior_scale'],
            'seasonality_mode': self.config['seasonality_mode'],
            'yearly_seasonality': self.config['yearly_seasonality'],
            'weekly_seasonality': self.config['weekly_seasonality'],
            'daily_seasonality': self.config['daily_seasonality'],
        }
        self.model = Prophet(**prophet_kwargs, holidays=holidays_df)

        if self.config.get('use_onpromotion') and onpromotion_series is not None:
            self.model.add_regressor('onpromotion')

        df = self._prepare_dataframe(train_series, onpromotion_series=onpromotion_series)
        with suppress_stdout_stderr():
            self.model.fit(df)

        self.train_series = train_series.copy()
        fitted_forecast = self.model.predict(df)
        fitted_values = np.maximum(0.0, fitted_forecast['yhat'].astype(float).to_numpy())
        self.fitted_values = pd.Series(fitted_values, index=train_series.index)

    def predict(self, steps=30, future_onpromotion=None):
        future_df = self.model.make_future_dataframe(periods=steps)
        future_df = future_df.tail(steps).copy()

        if self.config.get('use_onpromotion'):
            if future_onpromotion is None:
                promo_values = [0] * steps
            else:
                promo_values = list(future_onpromotion[:steps])
                if len(promo_values) < steps:
                    promo_values.extend([0] * (steps - len(promo_values)))
            future_df['onpromotion'] = promo_values

        forecast = self.model.predict(future_df)
        zero_series = pd.Series([0.0] * steps)

        return {
            'dates': [str(d.date()) for d in forecast['ds']],
            'forecast': [max(0.0, float(v)) for v in forecast['yhat']],
            'lower_ci': [max(0.0, float(v)) for v in forecast['yhat_lower']],
            'upper_ci': [max(0.0, float(v)) for v in forecast['yhat_upper']],
            'components': {
                'trend': [float(v) for v in forecast['trend']],
                'weekly': [float(v) for v in forecast.get('weekly', zero_series)],
                'yearly': [float(v) for v in forecast.get('yearly', zero_series)],
                'holidays': [float(v) for v in forecast.get('holidays', zero_series)],
            },
        }

    def get_changepoints(self):
        if self.model is None:
            return {'dates': [], 'deltas': []}

        changepoints = list(self.model.changepoints)
        deltas = list(self.model.params.get('delta', [[0.0] * len(changepoints)])[0])
        count = min(len(changepoints), len(deltas))
        return {
            'dates': [str(pd.to_datetime(changepoints[i]).date()) for i in range(count)],
            'deltas': [float(deltas[i]) for i in range(count)],
        }

    def evaluate(self, test_series, onpromotion_series=None):
        from modules.evaluator import ModelEvaluator

        future_df = pd.DataFrame({'ds': pd.to_datetime(test_series.index)})
        if self.config.get('use_onpromotion'):
            if onpromotion_series is not None:
                aligned = onpromotion_series.reindex(test_series.index).fillna(0)
                future_df['onpromotion'] = aligned.values
            else:
                future_df['onpromotion'] = [0] * len(future_df)

        forecast = self.model.predict(future_df)
        actual = np.array(test_series.values, dtype=float)
        predicted = np.maximum(0.0, forecast['yhat'].astype(float).to_numpy())
        metrics = ModelEvaluator.compute_all(actual, predicted, 'Prophet')
        metrics['predictions'] = [float(v) for v in predicted]
        metrics['dates'] = [str(pd.to_datetime(d).date()) for d in test_series.index]
        return metrics

    def save(self, model_path):
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        joblib.dump(self, model_path)

    @classmethod
    def load(cls, model_path):
        return joblib.load(model_path)

    @staticmethod
    def model_path(family, store_nbr):
        return os.path.join(DATA_MODELS_DIR, f'prophet_{safe_family_name(family)}_{store_nbr}.pkl')
