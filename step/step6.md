# Step 6 — 预测模型：LSTM（v3，扩展模块）

> **修订说明（v3）**：字段名适配 Favorita（`sales` 替代 `sales_qty`）；序列长度约1688点（略有提升，对 LSTM 略有帮助但仍属小样本）；文件命名约定更新；其余结构不变。

## 定位说明

**LSTM 在本项目中是"扩展对比模块"，不是主线**。

原因（诚实面对小样本现实）：
- 每个 (family, store_nbr) 序列约 1688 点，对 LSTM 来说数据量仍偏少
- 双层 LSTM 参数量约 33,000，1688 样本训练可能欠拟合或过拟合
- ��期表现：ARIMA ≈ Prophet > LSTM（小样本下 LSTM 不占优）

**论文中的处��方式**：
> "为完整性考虑，本文同时实现 LSTM 深度学习模型并纳入对比实验。受限于单品类单门店序列样本量（约 1688 天），LSTM 在本场景下的预测精度不如传统统计方法，但验证了深度学习方法在更大规模数据下的可扩展性。"

## 输入规格（锁死，不允许更改）

```
输入类型：单变量时间序列（pd.Series，DatetimeIndex，sales）
输入维度：(batch_size, seq_len, 1)  ← input_size=1，严格锁死
特征工程列（lag/rolling/onpromotion）：不使用
```

若需多变量扩展（input_size > 1），作为 TODO 在代码注释中说明，不在本次实现范围内。

## 核心类设计

### `LSTMNet(nn.Module)` — 网络定义

```python
class LSTMNet(nn.Module):
    """
    双层 LSTM + Dropout + 全连接输出
    
    ���入：(batch_size, seq_len, input_size=1)
    输出：(batch_size, 1)
    """
    def __init__(self, hidden_size=64, num_layers=2, dropout=0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=1,           # 单变量，锁死
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0
        )
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_size, 1)
    
    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(self.dropout(out[:, -1, :]))
```

### `LSTMModel` — 封装类

```python
class LSTMModel:
    def __init__(self, config: dict = None):
        """
        默认参数：
        {
          'seq_len': 30, 'hidden_size': 64, 'num_layers': 2,
          'dropout': 0.2, 'epochs': 50, 'batch_size': 32,
          'lr': 0.001, 'lr_patience': 10, 'early_stop_patience': 15,
          'device': 'cpu'
        }
        """
```

#### `_create_sequences(data, seq_len)` — 滑动窗口

```python
def _create_sequences(self, data: np.ndarray, seq_len: int):
    """
    data: 1D 归一化数组，shape (N,)
    返回：
      X: shape (N-seq_len, seq_len, 1)
      y: shape (N-seq_len,)
    """
    X, y = [], []
    for i in range(len(data) - seq_len):
        X.append(data[i:i+seq_len].reshape(-1, 1))
        y.append(data[i+seq_len])
    return np.array(X), np.array(y)
```

#### `fit(train_series, val_series, progress_callback=None)` — 训练

```python
训练流程：
1. MinMaxScaler.fit(train)，transform train/val（防数据泄漏）
2. _create_sequences 生成 X_train/y_train, X_val/y_val
3. 转为 torch.FloatTensor，DataLoader（train shuffle=True，val shuffle=False）
4. 初始化 LSTMNet, Adam, ReduceLROnPlateau(patience=lr_patience), MSELoss
5. 训练循环：
   for epoch in range(epochs):
     train_loss = 训练一轮（含梯度裁剪 max_norm=1.0）
     val_loss   = 验证一轮（model.eval(), no_grad）
     scheduler.step(val_loss)
     early_stopper(val_loss) → 触发则 break
     if progress_callback:
         progress_callback(epoch+1, epochs, train_loss, val_loss)
6. 保存 best model state（val_loss 最小时 deepcopy state_dict）

返回训练历史：
{
  'train_loss': [float, ...],
  'val_loss':   [float, ...],
  'best_epoch': int,
  'stopped_early': bool,
  'total_epochs':  int
}
```

#### `predict(steps=30)` — 递归预测

```python
递归滚动预测（单变量，无置信区间）：
  window = last seq_len values（归一化）
  predictions = []
  for _ in range(steps):
    x = tensor(window).unsqueeze(0)   # (1, seq_len, 1)
    pred = model(x).item()
    predictions.append(pred)
    window = np.append(window[1:], pred)  # 滑窗向前

反归一化后返回：
{
  'dates':    [str, ...],
  'forecast': [float, ...],   # 反归一化，clip ≥ 0
  # 无 lower_ci / upper_ci（递归预测无法提供置信区间）
  'model_params': {
    'seq_len': int, 'hidden_size': int,
    'num_layers': int, 'best_epoch': int
  }
}
```

> **前端处理**：LSTM 预测结果不显示置信区间阴影，仅显示预测折线。ARIMA/Prophet 显示置信带。

#### `evaluate(test_series)` — 测试集评估

使用**一步预测**（非递归）：每步用真实历史窗口预测下一步，消除误差积累影响：

```python
# 测试集 one-step-ahead（用于公平对比）
for i in range(len(test_scaled)):
    window = history[-seq_len:]          # 真实历史
    pred   = model(window)
    preds.append(pred)
    history.append(test_scaled[i])       # 加入真实值，不用预测值
```

#### `save(model_path, scaler_path)` / `load()`

```python
# 保存
torch.save(self.net.state_dict(), model_path)
joblib.dump(self.scaler, scaler_path)
json.dump(self.config, open(model_path + '.json', 'w'))

# 加载
config = json.load(open(model_path + '.json'))
net = LSTMNet(config['hidden_size'], config['num_layers'], config['dropout'])
net.load_state_dict(torch.load(model_path, map_location='cpu'))
```

文件命名约定：`lstm_{safe_family_name(family)}_{store_nbr}.pth`

> `safe_family_name()` 定义在 `config.py`，规则与 ARIMA/Prophet 完全一致，保证三种模型文件命名一一对应。

## 早停实现

```python
class EarlyStopping:
    def __init__(self, patience=15, min_delta=1e-5):
        self.patience = patience
        self.min_delta = min_delta
        self.counter = 0
        self.best_loss = float('inf')
        self.best_state = None
    
    def __call__(self, val_loss, model) -> bool:
        if val_loss < self.best_loss - self.min_delta:
            self.best_loss = val_loss
            self.best_state = deepcopy(model.state_dict())
            self.counter = 0
        else:
            self.counter += 1
        return self.counter >= self.patience
```

## 验收标准

- [ ] `LSTMNet` 前向传播：输入 `(8, 30, 1)` → 输出 `(8, 1)`，无报错
- [ ] `_create_sequences(data_len=100, seq_len=30)` → X.shape == (70, 30, 1)
- [ ] `fit()` train_loss 趋势下降（前10轮 > 后10轮均值）
- [ ] `fit()` 返回 training_history，含 train_loss 和 val_loss
- [ ] `predict(30)` 长度 = 30，无 NaN，所有值 ≥ 0
- [ ] `predict()` 返回中无 lower_ci / upper_ci 字段
- [ ] `evaluate()` 使用一步预测（not 递归）
- [ ] 50 epochs × 1688 样本，CPU 训练耗时 < 180 秒
- [ ] `LSTM_ENABLED=False` 时，Flask 路由跳过 LSTM，其余模型正常运行
