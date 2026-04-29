from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownArgumentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportAny=false, reportMissingTypeArgument=false, reportUnknownLambdaType=false, reportExplicitAny=false, reportArgumentType=false

import logging
import math
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

import numpy as np

from config import FAMILY_ZH_MAP


logger = logging.getLogger(__name__)


class ModelEvaluator:
    @staticmethod
    def _json_safe(v: Any) -> float | None:
        if v is None:
            return None
        try:
            value = float(v)
        except (TypeError, ValueError):
            return None
        if math.isnan(value) or math.isinf(value):
            return 0.0
        return value

    @staticmethod
    def _prepare_arrays(actual: Sequence[Any], predicted: Sequence[Any]) -> tuple[np.ndarray, np.ndarray]:
        actual_arr = np.asarray(actual, dtype=float).reshape(-1)
        predicted_arr = np.asarray(predicted, dtype=float).reshape(-1)
        if actual_arr.size == 0 or predicted_arr.size == 0:
            logger.warning("Empty inputs received for metric computation")
            return np.asarray([], dtype=float), np.asarray([], dtype=float)
        if actual_arr.size != predicted_arr.size:
            min_size = min(actual_arr.size, predicted_arr.size)
            logger.warning(
                "Mismatched input lengths: actual=%s predicted=%s; truncating to %s",
                actual_arr.size,
                predicted_arr.size,
                min_size,
            )
            actual_arr = actual_arr[:min_size]
            predicted_arr = predicted_arr[:min_size]
        return actual_arr, predicted_arr

    @staticmethod
    def mae(actual: Sequence[Any], predicted: Sequence[Any]) -> float:
        actual_arr, predicted_arr = ModelEvaluator._prepare_arrays(actual, predicted)
        if actual_arr.size == 0:
            return 0.0
        value = float(np.mean(np.abs(actual_arr - predicted_arr)))
        return ModelEvaluator._json_safe(value) or 0.0

    @staticmethod
    def rmse(actual: Sequence[Any], predicted: Sequence[Any]) -> float:
        actual_arr, predicted_arr = ModelEvaluator._prepare_arrays(actual, predicted)
        if actual_arr.size == 0:
            return 0.0
        value = np.sqrt(np.mean((actual_arr - predicted_arr) ** 2))
        return ModelEvaluator._json_safe(value) or 0.0

    @staticmethod
    def mape(actual: Sequence[Any], predicted: Sequence[Any]) -> float:
        """mean(|y - ŷ| / |y|) × 100, skipping actual=0 points to avoid explosion.
        When actual=0, MAPE is undefined; use SMAPE as a supplement for zero-heavy series."""
        actual_arr, predicted_arr = ModelEvaluator._prepare_arrays(actual, predicted)
        if actual_arr.size == 0:
            return 0.0
        # Skip actual=0 points (MAPE undefined there; SMAPE covers those cases)
        mask = np.abs(actual_arr) > 1e-8
        if not np.any(mask):
            logger.warning("All actual values are zero; MAPE undefined, returning 0.0. Use SMAPE instead.")
            return 0.0
        value = np.mean(np.abs(actual_arr[mask] - predicted_arr[mask]) / np.abs(actual_arr[mask])) * 100.0
        return ModelEvaluator._json_safe(value) or 0.0

    @staticmethod
    def smape(actual: Sequence[Any], predicted: Sequence[Any]) -> float:
        actual_arr, predicted_arr = ModelEvaluator._prepare_arrays(actual, predicted)
        if actual_arr.size == 0:
            return 0.0
        denominator = np.abs(actual_arr) + np.abs(predicted_arr) + 1e-8
        value = np.mean(2.0 * np.abs(actual_arr - predicted_arr) / denominator) * 100.0
        return ModelEvaluator._json_safe(value) or 0.0

    @staticmethod
    def r2(actual: Sequence[Any], predicted: Sequence[Any]) -> float:
        actual_arr, predicted_arr = ModelEvaluator._prepare_arrays(actual, predicted)
        if actual_arr.size == 0:
            return 0.0
        ss_res = np.sum((actual_arr - predicted_arr) ** 2)
        actual_mean = np.mean(actual_arr)
        ss_tot = np.sum((actual_arr - actual_mean) ** 2)
        if ModelEvaluator._json_safe(ss_tot) == 0.0:
            return 1.0 if ModelEvaluator.rmse(actual_arr, predicted_arr) == 0.0 else 0.0
        value = 1.0 - (ss_res / ss_tot)
        return ModelEvaluator._json_safe(value) or 0.0

    @staticmethod
    def compute_all(actual: Sequence[Any], predicted: Sequence[Any], model_name: str = '') -> dict[str, Any]:
        actual_arr, predicted_arr = ModelEvaluator._prepare_arrays(actual, predicted)
        sample_size = int(actual_arr.size)
        return {
            'model_name': str(model_name),
            'mae': float(ModelEvaluator.mae(actual_arr, predicted_arr)),
            'rmse': float(ModelEvaluator.rmse(actual_arr, predicted_arr)),
            'mape': float(ModelEvaluator.mape(actual_arr, predicted_arr)),
            'smape': float(ModelEvaluator.smape(actual_arr, predicted_arr)),
            'r2': float(ModelEvaluator.r2(actual_arr, predicted_arr)),
            'sample_size': sample_size,
        }

    @staticmethod
    def _normalize_for_radar(metrics: Mapping[str, Mapping[str, Any]]) -> dict[str, dict[str, float]]:
        normalized: dict[str, dict[str, float]] = {}
        if not metrics:
            return normalized

        metric_names = ['mae', 'rmse', 'mape', 'smape']
        model_names = set()
        for metric_values in metrics.values():
            model_names.update(metric_values.keys())

        for model_name in model_names:
            normalized[model_name] = {'mae': 0.0, 'rmse': 0.0, 'mape': 0.0, 'smape': 0.0, 'r2': 0.0}

        for metric_name in metric_names:
            values_dict = metrics.get(metric_name, {})
            safe_values = {
                model_name: float(ModelEvaluator._json_safe(values_dict.get(model_name, 0.0)) or 0.0)
                for model_name in model_names
            }
            if not safe_values:
                continue
            min_v = min(safe_values.values())
            max_v = max(safe_values.values())
            for model_name, value in safe_values.items():
                if max_v == min_v:
                    score = 1.0
                else:
                    score = (max_v - value) / (max_v - min_v)
                normalized[model_name][metric_name] = float(min(max(score, 0.0), 1.0))

        r2_values = metrics.get('r2', {})
        for model_name in model_names:
            r2_value = float(ModelEvaluator._json_safe(r2_values.get(model_name, 0.0)) or 0.0)
            normalized[model_name]['r2'] = float(min(max(r2_value, 0.0), 1.0))

        return normalized

    @staticmethod
    def compare_models(results: dict[str, dict[str, Any]]) -> dict[str, Any]:
        if not results:
            return {
                'metrics_table': [],
                'best_model': '',
                'best_reason': '综合评分最高（MAPE: 0.0%）',
                'bar_chart': {'models': [], 'mae': [], 'rmse': [], 'mape': []},
                'radar_chart': {
                    'indicators': [
                        {'name': 'MAE', 'max': 1},
                        {'name': 'RMSE', 'max': 1},
                        {'name': 'MAPE', 'max': 1},
                        {'name': 'SMAPE', 'max': 1},
                        {'name': 'R²', 'max': 1},
                    ],
                    'series': [],
                },
            }

        metric_names = ['mae', 'rmse', 'mape', 'smape', 'r2']
        model_names = list(results.keys())
        metrics = {
            metric_name: {
                model_name: float(ModelEvaluator._json_safe(results.get(model_name, {}).get(metric_name, 0.0)) or 0.0)
                for model_name in model_names
            }
            for metric_name in metric_names
        }

        scoring_metrics = ['mae', 'rmse', 'mape']
        normalized_scores = {model_name: {} for model_name in model_names}
        for metric_name in scoring_metrics:
            values = metrics[metric_name]
            min_v = min(values.values())
            max_v = max(values.values())
            for model_name, value in values.items():
                if max_v == min_v:
                    score = 1.0
                else:
                    score = (max_v - value) / (max_v - min_v)
                normalized_scores[model_name][metric_name] = float(min(max(score, 0.0), 1.0))

        metrics_table = []
        for model_name in model_names:
            if len(model_names) == 1:
                combined_score = 1.0
            else:
                combined_score = (
                    0.5 * normalized_scores[model_name]['mape']
                    + 0.3 * normalized_scores[model_name]['rmse']
                    + 0.2 * normalized_scores[model_name]['mae']
                )
            metrics_table.append(
                {
                    'model': str(model_name),
                    'rank': 0,
                    'mae': float(metrics['mae'][model_name]),
                    'rmse': float(metrics['rmse'][model_name]),
                    'mape': float(metrics['mape'][model_name]),
                    'smape': float(metrics['smape'][model_name]),
                    'r2': float(metrics['r2'][model_name]),
                    'score': float(ModelEvaluator._json_safe(combined_score) or 0.0),
                }
            )

        metrics_table.sort(key=lambda item: (-item['score'], item['mape'], item['rmse'], item['mae'], item['model']))
        for idx, item in enumerate(metrics_table, start=1):
            item['rank'] = idx

        best_entry = metrics_table[0]
        radar_normalized = ModelEvaluator._normalize_for_radar(metrics)
        radar_series = []
        for item in metrics_table:
            model_name = item['model']
            model_radar = radar_normalized.get(model_name, {})
            radar_series.append(
                {
                    'name': model_name,
                    'values': [
                        float(ModelEvaluator._json_safe(model_radar.get('mae', 0.0)) or 0.0),
                        float(ModelEvaluator._json_safe(model_radar.get('rmse', 0.0)) or 0.0),
                        float(ModelEvaluator._json_safe(model_radar.get('mape', 0.0)) or 0.0),
                        float(ModelEvaluator._json_safe(model_radar.get('smape', 0.0)) or 0.0),
                        float(ModelEvaluator._json_safe(model_radar.get('r2', 0.0)) or 0.0),
                    ],
                }
            )

        return {
            'metrics_table': metrics_table,
            'best_model': best_entry['model'],
            'best_reason': f"综合评分最高（MAPE: {best_entry['mape']:.1f}%）",
            'bar_chart': {
                'models': [item['model'] for item in metrics_table],
                'mae': [float(item['mae']) for item in metrics_table],
                'rmse': [float(item['rmse']) for item in metrics_table],
                'mape': [float(item['mape']) for item in metrics_table],
            },
            'radar_chart': {
                'indicators': [
                    {'name': 'MAE', 'max': 1},
                    {'name': 'RMSE', 'max': 1},
                    {'name': 'MAPE', 'max': 1},
                    {'name': 'SMAPE', 'max': 1},
                    {'name': 'R²', 'max': 1},
                ],
                'series': radar_series,
            },
        }

    @staticmethod
    def plot_predictions_comparison(
        actual: Sequence[Any],
        predictions: Mapping[str, Sequence[Any]],
        dates: Sequence[Any],
    ) -> dict[str, Any]:
        x_axis = [str(date) for date in dates]
        series = [
            {
                'name': '实际值',
                'data': [float(ModelEvaluator._json_safe(value) or 0.0) for value in actual],
                'type': 'line',
                'lineStyle': {'width': 2},
            }
        ]
        for model_name, values in (predictions or {}).items():
            series.append(
                {
                    'name': str(model_name),
                    'data': [float(ModelEvaluator._json_safe(value) or 0.0) for value in values],
                    'type': 'line',
                }
            )
        return {'xAxis': x_axis, 'series': series}

    @staticmethod
    def generate_evaluation_report(
        model_results: dict[str, dict[str, Any]],
        family: str,
        store_nbr: int,
        forecast_days: int,
    ) -> dict[str, Any]:
        metrics_result = ModelEvaluator.compare_models(model_results)
        return {
            'family': str(family),
            'family_zh': FAMILY_ZH_MAP.get(family, family),
            'store_nbr': int(store_nbr),
            'forecast_days': int(forecast_days),
            'evaluated_at': datetime.now().isoformat(),
            'metrics': metrics_result,
            'recommendation': {
                'best_model': metrics_result.get('best_model', ''),
                'reason': metrics_result.get('best_reason', ''),
                'note': '注：LSTM 为扩展对比模块，在小样本场景下预测精度可能低于统计模型',
            },
        }
