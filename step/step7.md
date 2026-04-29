# Step 7 — 模型评估与对比（v3）

> **修订说明（v3）**：字段名适配 Favorita（`sales` 替代 `sales_qty`）；其余评估逻辑不变，`ModelEvaluator` 为纯静态工具类，不依赖具体数据集字段。

## 目标
实现 `modules/evaluator.py`，提供统一的评估指标计算与多模型横向对比，输出 ECharts ��直接使��的图表数据。

## 核心类设计：`ModelEvaluator`（纯静态工具类）

### 基础指标

```python
@staticmethod
def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    """mean(|y - ŷ|)"""

@staticmethod
def rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    """sqrt(mean((y - ŷ)²))"""

@staticmethod
def mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """mean(|y - ŷ| / max(|y|, 1e-8)) × 100
    避免除零：actual=0 的点用 max(|y|, 1e-8) 而非跳过，
    防止 actual 全为 0 时返回 NaN。
    返回百分比值（如 12.5 表示 12.5%）
    """

@staticmethod
def smape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """mean(2|y-ŷ| / (|y|+|ŷ|+1e-8)) × 100"""

@staticmethod
def r2(actual: np.ndarray, predicted: np.ndarray) -> float:
    """1 - SS_res/SS_tot。注意：用于时���预测参考，不作为主排名指标"""
```

### `compute_all(actual, predicted, model_name='')` — 一次计算

```python
{
  'model_name': str,
  'mae':   float,
  'rmse':  float,
  'mape':  float,
  'smape': float,
  'r2':    float,
  'sample_size': int
}
```

### `compare_models(results: dict)` — 多模型对比

```python
@staticmethod
def compare_models(results: dict) -> dict:
    """
    接受动态模型集合：
    results = {
      'ARIMA':   {'mae': ..., 'rmse': ..., 'mape': ..., 'smape': ..., 'r2': ...},
      'Prophet': {...},
      # 'LSTM' 可选（LSTM_ENABLED=False 时不传入）
    }
    
    排名算法（综合评分）：
      对 MAE、RMSE、MAPE 三个指标分别归一化到 [0,1]：
        score_i = (max_v - v_i) / (max_v - min_v)  # 越小越好 → 分数越高
        edge case：max_v == min_v → score = 1.0（所有模型相同）
      综合得分 = 0.5×score_mape + 0.3×score_rmse + 0.2×score_mae
      rank 1 = 总分最高
    
    返回：
    {
      'metrics_table': [              # 用于前端表格，按 rank 升序
        {
          'model': 'Prophet', 'rank': 1,
          'mae': float, 'rmse': float, 'mape': float,
          'smape': float, 'r2': float, 'score': float
        }, ...
      ],
      'best_model': 'Prophet',
      'best_reason': '综合评分最高（MAPE: 7.1%）',
      'bar_chart': {                  # 误差对比柱状图
        'models': ['ARIMA', 'Prophet', ...],
        'mae':    [float, ...],
        'rmse':   [float, ...],
        'mape':   [float, ...]
      },
      'radar_chart': {                # 模型雷达图（仅有 ≥2 个模型时有意义）
        'indicators': [
          {'name': 'MAE',   'max': 1},
          {'name': 'RMSE',  'max': 1},
          {'name': 'MAPE',  'max': 1},
          {'name': 'SMAPE', 'max': 1},
          {'name': 'R²',    'max': 1}
        ],
        'series': [
          {'name': 'ARIMA',   'values': [float×5]},
          {'name': 'Prophet', 'values': [float×5]},
          ...
        ]
      }
    }
    """
```

**雷达图归一化细节**：
```python
def _normalize_for_radar(metrics: dict) -> dict:
    """
    MAE/RMSE/MAPE/SMAPE：越小越好 → (max-v)/(max-min)，范围 [0,1]
    R²：越大越好 → clip(r2, 0, 1)（负 R² 视为 0）
    """
```

### `plot_predictions_comparison(actual, predictions, dates)` — 预测对比图

```python
@staticmethod
def plot_predictions_comparison(actual: np.ndarray,
                                 predictions: dict,
                                 dates: list) -> dict:
    """
    predictions = {'ARIMA': [...], 'Prophet': [...], 'LSTM': [...]}  # 可选子集
    
    返回 ECharts 多系列折线图数据：
    {
      'xAxis': [str, ...],
      'series': [
        {'name': '实际值', 'data': [float,...], 'type': 'line', 'lineStyle': {'width': 2}},
        {'name': 'ARIMA',  'data': [float,...], 'type': 'line'},
        ...
      ]
    }
    """
```

### `generate_evaluation_report(model_results, family, store_nbr, forecast_days)` — 评估报告

```python
{
  'family':       str,    # 品类名（英文原始）
  'family_zh':    str,    # 品类名（中文）
  'store_nbr':    int,
  'forecast_days': int,
  'evaluated_at': str,
  'metrics':      compare_models() 的结果,
  'recommendation': {
    'best_model':  str,
    'reason':      str,
    'note':        '注：LSTM 为扩展对比模块，在小样本场景下预测精度可能低于统计模型'
  }
}
```

## 验收标准

- [ ] `mae([3,4,5], [2,4,6])` = 1.0
- [ ] `mape([0,100], [10,90])` 不报 ZeroDivisionError，对 actual=0 点使用 1e-8 保护
- [ ] `compare_models({'ARIMA': {...}, 'Prophet': {...}})` ranks 为 [1,2]，无重复
- [ ] `compare_models({'ARIMA': {...}})` 单模型时仍正常返回（rank=1）
- [ ] 雷达图 series 中所有值在 [0,1] 范围
- [ ] 所有返回值通过 `json.dumps()` 无异常（无 NaN、无 numpy 类型）
