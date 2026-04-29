# Step 4 — 预测模型：ARIMA（v3）

> **修订说明（v3）**：字段名适配 Favorita（`sales` 替代 `sales_qty`）；序列长度由约1096点升至约1688点，搜索时间上限说明更新；其余逻辑不变。

## 目标
实现 `modules/arima_model.py`，基于 statsmodels 对**单条时间序列**（某品类某门店的日销量）进行自动参数调优、训练与预测。

## 预测粒度（全局约定）

```
输入：pd.Series，DatetimeIndex，单品类-单门店的日 sales（约 1688 点）
输出：未来 N 天的点预测 + 95% 置信区间
```

> 如需预测"总销量"，调用方传入 `daily_total` 序列即可，模型本身不感知粒度。

## 核心类设计：`ARIMAModel`

```python
class ARIMAModel:
    def __init__(self, config: dict = None):
        """
        config 默认值（从 config.py 读取，可被参数覆盖）：
        {
          'p_range':   range(0, 4),
          'q_range':   range(0, 4),
          'd_range':   range(0, 3),
          'criterion': 'aic'          # 'aic' | 'bic'
        }
        state:
          self.order:         (p, d, q)（fit 后赋值）
          self.aic:           float
          self.bic:           float
          self.model_result:  ARIMAResultsWrapper
          self.train_series:  pd.Series
          self.fitted_values: pd.Series
          self._order_cache:  dict（key=series_hash，value=(p,d,q)）
        """
```

### `auto_select_order(series)` — 自动定阶

```
步骤 1：ADF 检验确定 d
  p_value < 0.05 → d = 0（平稳）
  否则对一阶差分再检验：
    p_value < 0.05 → d = 1
    否则 → d = 2

步骤 2：网格搜索 (p, q)（固定 d）
  for p in p_range, q in q_range:
    try:
      result = ARIMA(series, order=(p,d,q)).fit(method='innovations_mle')
      candidates.append((p, d, q, result.aic, result.bic))
    except (ValueError, np.linalg.LinAlgError, Exception):
      continue   # 不收敛则跳过，不报错

步骤 3：选最优 or Fallback
  if candidates:
    return min(candidates, key=lambda x: x[3 if criterion=='aic' else 4])[:3]
  else:
    logger.warning('ARIMA 全参数组合失败，使用 fallback ARIMA(1,1,1)')
    return (1, 1, 1)

缓存策略：
  series_hash = hash(series.values.tobytes())
  if series_hash in self._order_cache:
    return self._order_cache[series_hash]  # 跳过搜索
  ...
  self._order_cache[series_hash] = best_order
```

### `fit(train_series, order=None)`

- `order=None` → 调用 `auto_select_order()`
- 训练完成后记录 `self.order`, `self.aic`, `self.bic`, `self.fitted_values`

### `predict(steps=30)` — 样本外预测

```python
def predict(self, steps: int = 30) -> dict:
    forecast = self.model_result.get_forecast(steps=steps)
    mean     = forecast.predicted_mean
    ci       = forecast.conf_int(alpha=0.05)
    
    last_date = self.train_series.index[-1]
    dates = pd.date_range(last_date + pd.Timedelta(days=1), periods=steps)
    
    return {
        'dates':    [d.strftime('%Y-%m-%d') for d in dates],
        'forecast': [max(0.0, float(v)) for v in mean],       # clip ≥ 0
        'lower_ci': [max(0.0, float(v)) for v in ci.iloc[:,0]],
        'upper_ci': [max(0.0, float(v)) for v in ci.iloc[:,1]],
        'order':    list(self.order),
        'aic':      float(self.aic),
        'bic':      float(self.bic)
    }
```

### `get_fitted_vs_actual()` — 训练集拟合效果

```python
{
  'dates':  [str, ...],
  'actual': [float, ...],
  'fitted': [float, ...]   # clip ≥ 0
}
```

### `evaluate(test_series)` — 测试集滚动预测

```python
def evaluate(self, test_series: pd.Series) -> dict:
    """
    Rolling one-step-ahead forecast：
    对 test 中每一步，使用"真实历史 + 训练数据"预测下一步，
    不使用递归预测结果作为输入（消除误差积累）。
    
    返回 MAE/RMSE/MAPE/SMAPE（调用 ModelEvaluator.compute_all）
    """
```

### `save(filepath)` / `load(filepath)` — 序列化

```python
# 保存整个 ARIMAModel 对象（含 model_result）
joblib.dump(self, filepath)

@classmethod
def load(cls, filepath):
    return joblib.load(filepath)
```

文件命名约定：`arima_{safe_family_name(family)}_{store_nbr}.pkl`

> `safe_family_name()` 定义在 `config.py`，规则：大写保留、空格→下划线、逗号→下划线、移除其他非字母数字下划线字符。示例：`LIQUOR,WINE,BEER` → `LIQUOR_WINE_BEER`。

## ARIMA 局限性说明（写入 docstring，供论文引用）

1. **线性假设**：无法捕捉非线性关系（如促销爆发）
2. **短期优势**：7–30天预测通常优于复杂模型
3. **参数搜索代价**：48 组 × 单序列 < 90 秒（1688点比1096点略慢，已含缓存优化）

## 验收标准

- [ ] `auto_select_order()` 对平稳序列（白噪声）返回 `d=0`
- [ ] `auto_select_order()` 对随机游走序列返回 `d=1`
- [ ] 所有参数失败时返回 `(1,1,1)`，不抛异常
- [ ] `predict(30)` 长度 = 30，无 NaN，所有值 ≥ 0
- [ ] `evaluate()` 返回 4 个非负指标
- [ ] `save()` + `load()` 往返预测结果一致（误差 < 1e-4）
- [ ] 对 1688 点序列全流程耗时 < 90 秒
- [ ] 缓存生效：同序列第二次��用 `auto_select_order()` 不重新搜索
