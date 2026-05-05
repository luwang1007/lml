# 商贸公司销售数据分析与智能预测系统

## 项目简介
基于 Python Flask + Favorita 真实零售数据，实现多模型时间序列预测（ARIMA / Prophet / LSTM）与可视化分析的 Web 系统。

**毕业设计信息**：刘明亮，数据GT2401班

## 技术栈
- 后端：Python 3.10 + Flask
- 数据集：Kaggle Favorita Store Sales（5家门店子集，277,860行）
- 预测模型：ARIMA (statsmodels) / Prophet (Facebook) / LSTM (PyTorch)
- 前端：Bootstrap 5 + ECharts 5（离线可用）

## 目录结构
```text
.
├── app.py
├── config.py
├── modules/
│   ├── analyzer.py
│   ├── arima_model.py
│   ├── data_processor.py
│   ├── evaluator.py
│   ├── lstm_model.py
│   ├── prophet_model.py
│   └── task_manager.py
├── static/
├── templates/
├── tests/
│   ├── conftest.py
│   ├── test_api.py
│   ├── test_data_processor.py
│   ├── test_models.py
│   └── test_data/
├── prepare_data.py
└── requirements.txt
```

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 准备数据
从 Kaggle 下载 store-sales-time-series-forecasting 竞赛数据：
```bash
kaggle competitions download -c store-sales-time-series-forecasting
unzip store-sales-time-series-forecasting.zip -d data/raw/
python prepare_data.py
```

### 3. 安装可选依赖
Prophet：
```bash
pip install pystan==3.9.1
pip install prophet==1.1.5
# 若失败：在 config.py 设置 PROPHET_ENABLED = False
```

PyTorch（LSTM）：
```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu
# 若不需要：在 config.py 设置 LSTM_ENABLED = False
```

### 4. 启动系统
```bash
python app.py
```

访问 http://localhost:5000。若已存在 `data/raw/train_subset.csv`，首页可直接点击“加载内置演示数据”进入分析与预测流程，无需重新上传文件。

### 5. 运行测试
```bash
pip install pytest
pytest tests/ -v
```

本仓库已包含 Windows 虚拟环境时，也可运行：
```bash
./venv/Scripts/python.exe -m pytest tests -q
```

## 常见问题
| 问题 | 解决方案 |
|------|----------|
| Prophet 安装失败 | 先装 pystan==3.9.1，或设 PROPHET_ENABLED=False |
| 前端白屏 | 检查 static/vendor/ 目录是否有 echarts/bootstrap 文件 |
| 上传 xlsx 报错 | pip install openpyxl |
| LSTM 训练很慢 | 在 config.py 设置 LSTM_EPOCHS=20 |
| 找不到 train_subset.csv | 先下载 Kaggle 数据，再运行 prepare_data.py |

## 模型说明
- ARIMA：自动定阶，ADF检验确定差分次数，AIC准则选择最优(p,q)
- Prophet：集成Favorita节假日特征，支持onpromotion促销回归量
- LSTM：双层LSTM+EarlyStopping，单变量输入，扩展对比模块

## 数据集说明
Favorita Store Sales（5家门店，33个品类，2013-01-01至2017-08-15）  
总计 277,860 条记录
