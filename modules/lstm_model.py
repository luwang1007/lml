# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportPossiblyUnboundVariable=false, reportConstantRedefinition=false, reportAssignmentType=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false, reportUnknownParameterType=false, reportUntypedBaseClass=false, reportUnannotatedClassAttribute=false, reportMissingTypeArgument=false, reportUnusedCallResult=false, reportUnusedImport=false, reportMissingParameterType=false, reportAny=false
import json
import logging
import os
import sys
from copy import deepcopy
from datetime import timedelta

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.append(BASE_DIR)

from config import MODEL_DIR as DATA_MODELS_DIR, safe_family_name
from config import (
    LSTM_BATCH_SIZE,
    LSTM_EARLY_STOP_PAT,
    LSTM_EPOCHS,
    LSTM_HIDDEN_SIZE,
    LSTM_LR,
    LSTM_LR_PATIENCE,
    LSTM_NUM_LAYERS,
    LSTM_SEQ_LEN,
)


logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    from torch.utils.data import DataLoader, TensorDataset

    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning('PyTorch 未安装，LSTM 模型不可用。')


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


if TORCH_AVAILABLE:
    class LSTMNet(nn.Module):
        def __init__(self, hidden_size=64, num_layers=2, dropout=0.2):
            super().__init__()
            self.lstm = nn.LSTM(
                input_size=1,
                hidden_size=hidden_size,
                num_layers=num_layers,
                batch_first=True,
                dropout=dropout if num_layers > 1 else 0.0,
            )
            self.dropout = nn.Dropout(dropout)
            self.fc = nn.Linear(hidden_size, 1)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.fc(self.dropout(out[:, -1, :]))
else:
    LSTMNet = None


class LSTMModel:
    def __init__(self, config=None):
        default_config = {
            'seq_len': LSTM_SEQ_LEN,
            'hidden_size': LSTM_HIDDEN_SIZE,
            'num_layers': LSTM_NUM_LAYERS,
            'dropout': 0.2,
            'epochs': LSTM_EPOCHS,
            'batch_size': LSTM_BATCH_SIZE,
            'lr': LSTM_LR,
            'lr_patience': LSTM_LR_PATIENCE,
            'early_stop_patience': LSTM_EARLY_STOP_PAT,
            'device': 'auto',
        }
        self.config = {**default_config, **(config or {})}
        self.net = None
        self.scaler = None
        self.train_history = None
        self.last_seq = None
        self.train_end_date = None
        self.train_series = None

    def _resolve_device(self):
        requested = str(self.config.get('device', 'auto')).lower()
        if requested == 'auto':
            return torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        if requested.startswith('cuda') and not torch.cuda.is_available():
            logger.warning('配置要求使用 CUDA，但当前 CUDA 不可用，自动回退到 CPU。')
            return torch.device('cpu')
        return torch.device(requested)

    def _create_sequences(self, data, seq_len):
        X, y = [], []
        for i in range(len(data) - seq_len):
            X.append(data[i:i + seq_len].reshape(-1, 1))
            y.append(data[i + seq_len])
        return np.array(X), np.array(y)

    def fit(self, train_series, val_series, progress_callback=None) -> dict:
        if not TORCH_AVAILABLE:
            raise ImportError('PyTorch 未安装，LSTM 模型不可用')

        train_values = np.asarray(train_series.values, dtype=float).reshape(-1)
        val_values = np.asarray(val_series.values, dtype=float).reshape(-1)
        seq_len = int(self.config['seq_len'])

        min_len = min(train_values.size, val_values.size)
        if min_len <= 1:
            raise ValueError(f'train_series 或 val_series 长度不足，无法训练 LSTM（最少需要 2 个点）')
        if min_len <= seq_len:
            seq_len = max(1, min_len - 1)
            logger.warning('序列长度（%d）≤ seq_len（%d），自动降级为 seq_len=%d', min_len, self.config['seq_len'], seq_len)
            self.config = {**self.config, 'seq_len': seq_len}

        scaler = MinMaxScaler()
        scaler.fit(train_values.reshape(-1, 1))
        train_scaled = scaler.transform(train_values.reshape(-1, 1)).flatten()
        val_scaled = scaler.transform(val_values.reshape(-1, 1)).flatten()

        X_train, y_train = self._create_sequences(train_scaled, seq_len)
        X_val, y_val = self._create_sequences(val_scaled, seq_len)

        device = self._resolve_device()
        self.config['device'] = str(device)
        train_dataset = TensorDataset(
            torch.FloatTensor(X_train),
            torch.FloatTensor(y_train),
        )
        val_dataset = TensorDataset(
            torch.FloatTensor(X_val),
            torch.FloatTensor(y_val),
        )
        train_loader = DataLoader(train_dataset, batch_size=int(self.config['batch_size']), shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=int(self.config['batch_size']), shuffle=False)

        net = LSTMNet(
            hidden_size=int(self.config['hidden_size']),
            num_layers=int(self.config['num_layers']),
            dropout=float(self.config['dropout']),
        ).to(device)
        optimizer = torch.optim.Adam(net.parameters(), lr=float(self.config['lr']))
        scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(
            optimizer,
            patience=int(self.config['lr_patience']),
            factor=0.5,
        )
        criterion = nn.MSELoss()
        early_stopper = EarlyStopping(patience=int(self.config['early_stop_patience']))

        train_losses, val_losses = [], []
        best_epoch = 0
        epochs = int(self.config['epochs'])
        early_stop_patience = int(self.config['early_stop_patience'])

        for epoch in range(epochs):
            net.train()
            epoch_loss = 0.0
            for xb, yb in train_loader:
                xb = xb.to(device)
                yb = yb.to(device)
                optimizer.zero_grad()
                pred = net(xb).squeeze(-1)
                loss = criterion(pred, yb)
                loss.backward()
                torch.nn.utils.clip_grad_norm_(net.parameters(), max_norm=1.0)
                optimizer.step()
                epoch_loss += float(loss.item())
            train_loss = epoch_loss / len(train_loader)

            net.eval()
            with torch.no_grad():
                val_loss_total = 0.0
                for xb, yb in val_loader:
                    xb = xb.to(device)
                    yb = yb.to(device)
                    val_loss_total += float(criterion(net(xb).squeeze(-1), yb).item())
            val_loss = val_loss_total / len(val_loader)

            train_losses.append(float(train_loss))
            val_losses.append(float(val_loss))
            scheduler.step(val_loss)

            if progress_callback:
                progress_callback(epoch + 1, epochs, float(train_loss), float(val_loss))

            if early_stopper(val_loss, net):
                best_epoch = epoch + 1 - early_stop_patience
                break
        else:
            best_epoch = epochs

        if early_stopper.best_state:
            net.load_state_dict(early_stopper.best_state)

        self.net = net
        self.scaler = scaler
        self.train_history = {
            'train_loss': [float(v) for v in train_losses],
            'val_loss': [float(v) for v in val_losses],
            'best_epoch': int(max(1, best_epoch)),
            'stopped_early': bool(early_stopper.counter >= early_stopper.patience),
            'total_epochs': int(len(train_losses)),
            'device': str(device),
            'cuda_device_name': torch.cuda.get_device_name(device) if device.type == 'cuda' else None,
        }
        self.last_seq = train_scaled[-seq_len:].copy()
        self.train_end_date = train_series.index[-1]
        self.train_series = train_series.copy()
        return dict(self.train_history)

    def predict(self, steps=30) -> dict:
        if not TORCH_AVAILABLE:
            raise ImportError('PyTorch 未安装，LSTM 模型不可用')
        if self.net is None or self.scaler is None or self.last_seq is None or self.train_end_date is None:
            raise ValueError('模型尚未训练或缺少预测所需状态')

        steps = int(steps)
        window = self.last_seq.copy()
        predictions = []
        device = next(self.net.parameters()).device

        self.net.eval()
        with torch.no_grad():
            for _ in range(steps):
                x = torch.FloatTensor(window).unsqueeze(0).unsqueeze(-1).to(device)
                pred = float(self.net(x).item())
                predictions.append(pred)
                window = np.append(window[1:], pred)

        preds_orig = self.scaler.inverse_transform(np.array(predictions).reshape(-1, 1)).flatten()
        future_dates = pd.date_range(self.train_end_date + timedelta(days=1), periods=steps)
        return {
            'dates': [str(d.date()) for d in future_dates],
            'forecast': [max(0.0, float(v)) for v in preds_orig],
            'model_params': {
                'seq_len': int(self.config['seq_len']),
                'hidden_size': int(self.config['hidden_size']),
                'num_layers': int(self.config['num_layers']),
                'best_epoch': self.train_history.get('best_epoch', 0) if self.train_history else 0,
                'device': str(device),
                'cuda_device_name': torch.cuda.get_device_name(device) if device.type == 'cuda' else None,
            },
        }

    def evaluate(self, test_series) -> dict:
        if not TORCH_AVAILABLE:
            raise ImportError('PyTorch 未安装，LSTM 模型不可用')
        if self.net is None or self.scaler is None or self.train_series is None:
            raise ValueError('模型尚未训练，无法评估')

        from modules.evaluator import ModelEvaluator

        seq_len = int(self.config['seq_len'])
        train_values = np.asarray(self.train_series.values, dtype=float).reshape(-1)
        test_values = np.asarray(test_series.values, dtype=float).reshape(-1)
        history = np.concatenate([train_values[-seq_len:], test_values])
        predictions = []
        device = next(self.net.parameters()).device

        self.net.eval()
        with torch.no_grad():
            for i in range(seq_len, len(history)):
                window = history[i - seq_len:i]
                window_scaled = self.scaler.transform(window.reshape(-1, 1)).flatten()
                x = torch.FloatTensor(window_scaled).unsqueeze(0).unsqueeze(-1).to(device)
                pred_scaled = float(self.net(x).item())
                pred_value = float(self.scaler.inverse_transform(np.array([[pred_scaled]])).flatten()[0])
                predictions.append(max(0.0, pred_value))

        metrics = ModelEvaluator.compute_all(
            np.asarray(test_values, dtype=float),
            np.asarray(predictions, dtype=float),
            'LSTM',
        )
        metrics['predictions'] = [float(v) for v in predictions]
        metrics['dates'] = [str(pd.to_datetime(d).date()) for d in test_series.index]
        return metrics

    def use_recent_history_for_forecast(self, series) -> None:
        if self.scaler is None:
            raise ValueError('模型尚未训练，无法更新预测历史窗口')
        seq_len = int(self.config['seq_len'])
        values = np.asarray(series.values, dtype=float).reshape(-1, 1)
        if len(values) < seq_len:
            raise ValueError(f'历史序列长度不足，无法构造 LSTM 预测窗口（需要至少 {seq_len} 个点）')
        scaled = self.scaler.transform(values).flatten()
        self.last_seq = scaled[-seq_len:].copy()
        self.train_end_date = series.index[-1]

    def save(self, model_path, scaler_path=None) -> None:
        if not TORCH_AVAILABLE:
            raise ImportError('PyTorch 未安装，LSTM 模型不可用')
        if self.net is None or self.scaler is None:
            raise ValueError('模型尚未训练，无法保存')

        if scaler_path is None:
            scaler_path = model_path + '.scaler.pkl'
        config_path = model_path + '.json'
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        torch.save(self.net.state_dict(), model_path)
        joblib.dump(self.scaler, scaler_path)
        with open(config_path, 'w', encoding='utf-8') as fp:
            json.dump(self.config, fp)

    @classmethod
    def load(cls, model_path, scaler_path=None) -> 'LSTMModel':
        if not TORCH_AVAILABLE:
            raise ImportError('PyTorch 未安装，LSTM 模型不可用')

        if scaler_path is None:
            scaler_path = model_path + '.scaler.pkl'
        config_path = model_path + '.json'
        with open(config_path, 'r', encoding='utf-8') as fp:
            config = json.load(fp)
        obj = cls(config)
        net = LSTMNet(config['hidden_size'], config['num_layers'], config['dropout'])
        net.load_state_dict(torch.load(model_path, map_location='cpu'))
        net = net.to(obj._resolve_device())
        net.eval()
        obj.net = net
        obj.scaler = joblib.load(scaler_path)
        return obj

    @staticmethod
    def model_path(family, store_nbr) -> str:
        return os.path.join(DATA_MODELS_DIR, f'lstm_{safe_family_name(family)}_{store_nbr}.pth')
