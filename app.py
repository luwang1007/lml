# pyright: reportMissingImports=false, reportMissingTypeStubs=false, reportUnknownParameterType=false, reportMissingParameterType=false, reportUnknownVariableType=false, reportUnknownArgumentType=false, reportUnknownMemberType=false, reportAny=false, reportOptionalSubscript=false, reportUnusedVariable=false, reportUnusedParameter=false, reportCallIssue=false, reportArgumentType=false, reportPossiblyUnboundVariable=false, reportUnusedCallResult=false

import io
import hashlib
import json
import logging
import math
import os
import threading
import uuid
from datetime import datetime

import pandas as pd
from flask import Flask, jsonify, render_template, request, send_file, session

from config import (
    ALLOWED_EXTENSIONS, DATA_PROC_DIR as DATA_PROCESSED_DIR, FORECAST_DAYS,
    LSTM_ENABLED, MAX_CONTENT_LENGTH, PROPHET_ENABLED, SECRET_KEY,
    FAMILY_ZH_MAP, MODEL_DIR, safe_family_name,
)
from modules.analyzer import DataAnalyzer
from modules.arima_model import ARIMAModel
from modules.data_processor import DataProcessor
from modules.evaluator import ModelEvaluator
from modules.task_manager import TaskManager

if PROPHET_ENABLED:
    from modules.prophet_model import PROPHET_AVAILABLE, ProphetModel
else:
    PROPHET_AVAILABLE = False

if LSTM_ENABLED:
    from modules.lstm_model import TORCH_AVAILABLE, LSTMModel
else:
    TORCH_AVAILABLE = False

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH


def _sanitize_json(value):
    if value is None:
        return None
    if isinstance(value, dict):
        return {str(k): _sanitize_json(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_json(v) for v in value]
    if isinstance(value, pd.DataFrame):
        return _sanitize_json(value.to_dict(orient='records'))
    if isinstance(value, pd.Series):
        return _sanitize_json(value.tolist())
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if hasattr(value, 'item'):
        try:
            value = value.item()
        except Exception:
            pass
    if isinstance(value, float):
        return None if math.isnan(value) or math.isinf(value) else value
    return value


def _ok(data=None):
    return jsonify({'code': 200, 'message': 'ok', 'data': _sanitize_json(data)})


def _err(code, message):
    return jsonify({'code': code, 'message': str(message), 'data': None}), code


def _analysis_result(result):
    if isinstance(result, dict) and result.get('success') is True:
        return _ok(result.get('data', {}))
    if isinstance(result, dict) and result.get('success') is False:
        return _err(400, result.get('error', '分析失败'))
    return _ok(result)


def _get_df(session_id=None):
    meta_path = session.get('meta_path')
    if not meta_path or not os.path.exists(meta_path):
        return None, _err(404, '会话已过期，请重新上传数据')
    try:
        df = DataProcessor.load_processed(meta_path)
        return df, None
    except Exception as e:
        return None, _err(500, f'数据加载失败：{e}')


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/analysis')
def analysis():
    return render_template('analysis.html')


@app.route('/prediction')
def prediction():
    return render_template('prediction.html')


@app.route('/report')
def report():
    return render_template('report.html')


@app.route('/api/upload', methods=['POST'])
def upload():
    if 'file' not in request.files:
        return _err(400, '请选择要上传的文件')
    f = request.files['file']
    if f.filename == '':
        return _err(400, '请选择要上传的文件')

    ext = os.path.splitext(f.filename)[1].lower()
    if ext == '.xls':
        return _err(400, '不支持 .xls 格式，请另存为 .xlsx 再上传')
    allowed_suffixes = {f'.{item.lower()}' for item in ALLOWED_EXTENSIONS}
    if ext not in allowed_suffixes:
        return _err(400, '文件格式不支持，请上传 CSV 或 xlsx 文件')

    session_id = str(uuid.uuid4())
    tmp_path = os.path.join(DATA_PROCESSED_DIR, f'upload_{session_id}{ext}')
    os.makedirs(DATA_PROCESSED_DIR, exist_ok=True)
    f.save(tmp_path)

    try:
        processor = DataProcessor(tmp_path, session_id=session_id)
        meta_path, validation = processor.process()
        session['meta_path'] = meta_path
        summary = DataProcessor.load_processed(meta_path)
        return _ok({
            'session_id': session_id,
            'summary': _load_summary_from_meta(meta_path),
            'validation': validation,
            'rows': len(summary),
        })
    except ValueError as e:
        return _err(400, str(e))
    except Exception as e:
        logger.exception('Upload error')
        return _err(500, f'处理失败：{e}')
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _load_summary_from_meta(meta_path):
    with open(meta_path, encoding='utf-8') as fp:
        meta = json.load(fp)
    return meta.get('summary', {})


def _stable_json(value):
    return json.dumps(_sanitize_json(value), ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _series_fingerprint(series):
    hasher = hashlib.sha256()
    hasher.update(str(len(series)).encode('utf-8'))
    if len(series):
        hasher.update(str(series.index[0]).encode('utf-8'))
        hasher.update(str(series.index[-1]).encode('utf-8'))
    hasher.update(pd.util.hash_pandas_object(series, index=True).values.tobytes())
    return hasher.hexdigest()[:16]


def _cache_key(model_name, family, store_nbr, series, model_config):
    payload = {
        'version': 2,
        'model': model_name,
        'family': family,
        'store_nbr': int(store_nbr),
        'series_fingerprint': _series_fingerprint(series),
        'config': _sanitize_json(model_config or {}),
    }
    return hashlib.sha256(_stable_json(payload).encode('utf-8')).hexdigest()[:16]


def _cache_paths(model_name, family, store_nbr, cache_key):
    safe_model = model_name.lower()
    safe_family = safe_family_name(family)
    prefix = f'{safe_model}_{safe_family}_{int(store_nbr)}_{cache_key}'
    ext = '.pth' if model_name == 'LSTM' else '.pkl'
    return {
        'model': os.path.join(MODEL_DIR, prefix + ext),
        'meta': os.path.join(MODEL_DIR, prefix + '.meta.json'),
    }


def _load_model_cache(model_name, paths):
    if not os.path.exists(paths['meta']) or not os.path.exists(paths['model']):
        return None, None
    try:
        with open(paths['meta'], encoding='utf-8') as fp:
            meta = json.load(fp)
        if model_name == 'ARIMA':
            model = ARIMAModel.load(paths['model'])
        elif model_name == 'Prophet':
            model = ProphetModel.load(paths['model'])
        elif model_name == 'LSTM':
            model = LSTMModel.load(paths['model'])
        else:
            return None, None
        return model, meta
    except Exception as exc:
        logger.warning('加载模型缓存失败，将重新训练 %s: %s', model_name, exc)
        return None, None


def _save_model_cache(model_name, model, paths, meta):
    os.makedirs(MODEL_DIR, exist_ok=True)
    model.save(paths['model'])
    meta = {
        **_sanitize_json(meta),
        'model_name': model_name,
        'model_path': paths['model'],
        'saved_at': datetime.now().isoformat(),
    }
    with open(paths['meta'], 'w', encoding='utf-8') as fp:
        json.dump(meta, fp, ensure_ascii=False, indent=2)


@app.route('/api/data/summary')
def data_summary():
    df, err = _get_df()
    if err:
        return err
    meta_path = session.get('meta_path')
    with open(meta_path, encoding='utf-8') as fp:
        meta = json.load(fp)
    return _ok(meta.get('summary', {}))


@app.route('/api/analysis/overview')
def analysis_overview():
    df, err = _get_df()
    if err:
        return err
    analyzer = DataAnalyzer(df)
    return _analysis_result(analyzer.get_overview_stats())


@app.route('/api/analysis/trend')
def analysis_trend():
    df, err = _get_df()
    if err:
        return err
    granularity = request.args.get('granularity', 'monthly')
    family = request.args.get('family', 'all')
    store_nbr = int(request.args.get('store_nbr', 0))
    family = 'all' if family == 'all' else family
    store_nbr = 0 if store_nbr == 0 else store_nbr
    analyzer = DataAnalyzer(df)
    return _analysis_result(analyzer.get_trend_chart(granularity, family, store_nbr))


@app.route('/api/analysis/monthly_comparison')
def analysis_monthly():
    df, err = _get_df()
    if err:
        return err
    return _analysis_result(DataAnalyzer(df).get_monthly_comparison())


@app.route('/api/analysis/category_pie')
def analysis_pie():
    df, err = _get_df()
    if err:
        return err
    return _analysis_result(DataAnalyzer(df).get_category_pie())


@app.route('/api/analysis/top_families')
def analysis_top_families():
    df, err = _get_df()
    if err:
        return err
    n = min(33, max(1, int(request.args.get('n', 10))))
    return _analysis_result(DataAnalyzer(df).get_top_families(n))


@app.route('/api/analysis/correlation')
def analysis_correlation():
    df, err = _get_df()
    if err:
        return err
    return _analysis_result(DataAnalyzer(df).get_correlation_heatmap())


@app.route('/api/analysis/weekday')
def analysis_weekday():
    df, err = _get_df()
    if err:
        return err
    return _analysis_result(DataAnalyzer(df).get_weekday_pattern())


@app.route('/api/analysis/seasonal')
def analysis_seasonal():
    df, err = _get_df()
    if err:
        return err
    family = request.args.get('family', 'all')
    store_nbr = int(request.args.get('store_nbr', 0))
    period = int(request.args.get('period', 7))
    family = None if family == 'all' else family
    store_nbr = None if store_nbr == 0 else store_nbr
    return _analysis_result(DataAnalyzer(df).get_seasonal_decomposition(family, store_nbr, period))


@app.route('/api/analysis/promotion')
def analysis_promotion():
    df, err = _get_df()
    if err:
        return err
    family = request.args.get('family', 'all')
    family = None if family == 'all' else family
    return _analysis_result(DataAnalyzer(df).get_promotion_effect(family))


@app.route('/api/analysis/adf')
def analysis_adf():
    df, err = _get_df()
    if err:
        return err
    family = request.args.get('family')
    store_nbr = request.args.get('store_nbr')
    if not family or not store_nbr:
        return _err(400, 'family 和 store_nbr 参数必填')
    store_nbr = int(store_nbr)
    from statsmodels.tsa.stattools import adfuller
    from config import COL_DATE, COL_FAMILY, COL_STORE, COL_SALES

    mask = (df[COL_FAMILY] == family) & (df[COL_STORE] == store_nbr)
    series = df[mask].set_index(COL_DATE)[COL_SALES].sort_index()
    if len(series) < 20:
        return _err(400, f'品类 {family} 门店 {store_nbr} 数据不足，无法进行 ADF 检验')
    try:
        result = adfuller(series.dropna())
        adf_stat = float(result[0])
        p_value = float(result[1])
        is_stationary = p_value < 0.05
        suggested_d = 0 if is_stationary else 1
        conclusion = (
            f'序列平稳（p={p_value:.4f} < 0.05），ARIMA 建议 d=0'
            if is_stationary else
            f'序列不平稳（p={p_value:.4f} ≥ 0.05），ARIMA 建议 d=1'
        )
        return _ok({
            'adf_statistic': adf_stat,
            'p_value': p_value,
            'is_stationary': is_stationary,
            'conclusion': conclusion,
            'suggested_d': suggested_d,
        })
    except Exception as e:
        return _err(500, f'ADF 检验失败：{e}')


@app.route('/api/predict/start', methods=['POST'])
def predict_start():
    body = request.get_json(silent=True) or {}
    session_id_req = body.get('session_id')
    family = body.get('family')
    store_nbr = body.get('store_nbr')
    forecast_days = int(body.get('forecast_days', FORECAST_DAYS))
    models_req = body.get('models', ['ARIMA', 'Prophet'])
    arima_config = body.get('arima_config', {})
    prophet_config = body.get('prophet_config', {})
    lstm_config = body.get('lstm_config', {})

    if not family:
        return _err(400, 'family 参数必填')
    if not store_nbr:
        return _err(400, 'store_nbr 参数必填')
    store_nbr = int(store_nbr)
    if not models_req:
        return _err(400, '至少选择一个预测模型')
    allowed_models = {'ARIMA', 'Prophet', 'LSTM'}
    invalid = [m for m in models_req if m not in allowed_models]
    if invalid:
        return _err(400, f'不支持的模型：{", ".join(invalid)}')
    if not 7 <= forecast_days <= 90:
        return _err(400, '预测天数需在 7–90 之间')
    if 'Prophet' in models_req:
        if not PROPHET_ENABLED:
            return _err(400, 'Prophet 模块未启用，请在 config.py 设置 PROPHET_ENABLED=True')
        if not PROPHET_AVAILABLE:
            return _err(400, 'Prophet 未安装，请先安装 prophet，或取消选择 Prophet 模型')
    if 'LSTM' in models_req:
        if not LSTM_ENABLED:
            return _err(400, 'LSTM 模块未启用，请在 config.py 设置 LSTM_ENABLED=True')
        if not TORCH_AVAILABLE:
            return _err(400, 'PyTorch 未安装，请先安装 torch，或取消选择 LSTM 模型')

    meta_path = session.get('meta_path')
    if not meta_path or not os.path.exists(meta_path):
        return _err(404, '会话已过期，请重新上传数据')
    df = DataProcessor.load_processed(meta_path)

    from config import COL_FAMILY, COL_STORE
    if family not in df[COL_FAMILY].unique():
        return _err(400, f'品类不存在：{family}，请重新选择')
    if store_nbr not in df[COL_STORE].unique():
        return _err(400, f'门店不存在：{store_nbr}，请重新选择')

    task_id = TaskManager.create()
    t = threading.Thread(
        target=_run_prediction,
        args=(
            task_id, df, family, store_nbr, forecast_days, models_req,
            arima_config, prophet_config, lstm_config,
        ),
        daemon=True,
    )
    t.start()
    return _ok({'task_id': task_id, 'session_id': session_id_req})


def _run_prediction(task_id, df, family, store_nbr, forecast_days,
                    models_req, arima_config, prophet_config, lstm_config):
    from config import COL_DATE, COL_FAMILY, COL_STORE, COL_SALES, COL_ONPROMO, TRAIN_RATIO, VAL_RATIO

    try:
        if TaskManager.is_cancelled(task_id):
            return

        TaskManager.update(task_id, 0, '数据准备中...', {m: 'pending' for m in models_req})
        mask = (df[COL_FAMILY] == family) & (df[COL_STORE] == store_nbr)
        series = df[mask].set_index(COL_DATE)[COL_SALES].sort_index()

        onpromo_series = None
        if COL_ONPROMO in df.columns:
            onpromo_series = df[mask].set_index(COL_DATE)[COL_ONPROMO].sort_index()

        n = len(series)
        if n < 30:
            raise ValueError(f'当前品类/门店序列只有 {n} 个点，至少需要 30 个点才能训练和评估')
        train_end = int(n * TRAIN_RATIO)
        val_end = int(n * (TRAIN_RATIO + VAL_RATIO))
        train = series.iloc[:train_end]
        val = series.iloc[train_end:val_end]
        test = series.iloc[val_end:]
        if train.empty or val.empty or test.empty:
            raise ValueError('训练集、验证集或测试集为空，请上传更长时间跨度的数据')

        train_promo = onpromo_series.iloc[:train_end] if onpromo_series is not None else None
        test_promo  = onpromo_series.iloc[val_end:]   if onpromo_series is not None else None
        TaskManager.update(task_id, 5, '数据准备完成', {m: 'pending' for m in models_req})

        if TaskManager.is_cancelled(task_id):
            return

        n_models = len(models_req)
        progress_per_model = 85 // n_models
        model_results = {}
        model_predictions = {}
        model_status = {m: 'pending' for m in models_req}
        current_progress = 5

        for model_name in models_req:
            if TaskManager.is_cancelled(task_id):
                return
            model_status[model_name] = 'running'
            TaskManager.update(task_id, current_progress, f'训练 {model_name} 模型...', model_status.copy())

            if model_name == 'ARIMA':
                cache_key = _cache_key(model_name, family, store_nbr, series, arima_config)
                paths = _cache_paths(model_name, family, store_nbr, cache_key)
                final_model, cache_meta = _load_model_cache(model_name, paths)
                if final_model and cache_meta:
                    TaskManager.update(task_id, current_progress, f'加载 {model_name} 缓存模型...', model_status.copy())
                    metrics = cache_meta['metrics']
                    cache_hit = True
                else:
                    model = ARIMAModel(arima_config)
                    model.fit(train)
                    metrics = model.evaluate(test)
                    final_model = ARIMAModel(arima_config)
                    final_model.fit(series, order=model.order)
                    _save_model_cache(model_name, final_model, paths, {
                        'cache_key': cache_key,
                        'family': family,
                        'store_nbr': store_nbr,
                        'config': arima_config,
                        'metrics': metrics,
                        'series_fingerprint': _series_fingerprint(series),
                    })
                    cache_hit = False
                pred = final_model.predict(forecast_days)
                fitted = final_model.get_fitted_vs_actual()
                model_predictions[model_name] = {
                    **pred,
                    'order': list(final_model.order) if final_model.order else None,
                    'aic': float(final_model.aic) if getattr(final_model, 'aic', None) is not None else None,
                    'fitted_vs_actual': fitted,
                    'cache_hit': cache_hit,
                }

            elif model_name == 'Prophet':
                if TaskManager.is_cancelled(task_id):
                    return
                cache_key = _cache_key(model_name, family, store_nbr, series, prophet_config)
                paths = _cache_paths(model_name, family, store_nbr, cache_key)
                final_model, cache_meta = _load_model_cache(model_name, paths)
                if final_model and cache_meta:
                    TaskManager.update(task_id, current_progress, f'加载 {model_name} 缓存模型...', model_status.copy())
                    metrics = cache_meta['metrics']
                    cache_hit = True
                else:
                    model = ProphetModel(prophet_config)
                    model.fit(train, onpromotion_series=train_promo)
                    metrics = model.evaluate(test, onpromotion_series=test_promo)
                    final_model = ProphetModel(prophet_config)
                    final_model.fit(series, onpromotion_series=onpromo_series)
                    _save_model_cache(model_name, final_model, paths, {
                        'cache_key': cache_key,
                        'family': family,
                        'store_nbr': store_nbr,
                        'config': prophet_config,
                        'metrics': metrics,
                        'series_fingerprint': _series_fingerprint(series),
                    })
                    cache_hit = False
                pred = final_model.predict(forecast_days)
                changepoints = final_model.get_changepoints()
                model_predictions[model_name] = {
                    **pred,
                    'changepoints': changepoints,
                    'cache_hit': cache_hit,
                }

            elif model_name == 'LSTM':
                if TaskManager.is_cancelled(task_id):
                    return
                cache_key = _cache_key(model_name, family, store_nbr, series, lstm_config)
                paths = _cache_paths(model_name, family, store_nbr, cache_key)
                model, cache_meta = _load_model_cache(model_name, paths)
                if model and cache_meta:
                    TaskManager.update(task_id, current_progress, f'加载 {model_name} 缓存模型...', model_status.copy())
                    metrics = cache_meta['metrics']
                    history = cache_meta.get('training_history', {})
                    cache_hit = True
                else:
                    model = LSTMModel(lstm_config)
                    history = model.fit(train, val)
                    metrics = model.evaluate(test)
                    _save_model_cache(model_name, model, paths, {
                        'cache_key': cache_key,
                        'family': family,
                        'store_nbr': store_nbr,
                        'config': model.config,
                        'metrics': metrics,
                        'training_history': history,
                        'series_fingerprint': _series_fingerprint(series),
                    })
                    cache_hit = False
                model.use_recent_history_for_forecast(series)
                pred = model.predict(forecast_days)
                model_predictions[model_name] = {
                    **pred,
                    'training_history': {
                        'epochs': list(range(1, len(history.get('train_loss', [])) + 1)),
                        'train_loss': history.get('train_loss', []),
                        'val_loss': history.get('val_loss', []),
                        'device': history.get('device'),
                        'cuda_device_name': history.get('cuda_device_name'),
                    },
                    'cache_hit': cache_hit,
                }

            else:
                raise ValueError(f'不支持的模型：{model_name}')

            model_results[model_name] = metrics
            model_status[model_name] = 'done'
            current_progress += progress_per_model
            TaskManager.update(task_id, current_progress, f'{model_name} 完成', model_status.copy())

        if TaskManager.is_cancelled(task_id):
            return
        TaskManager.update(task_id, 90, '计算评估指标...', model_status.copy())

        eval_results = ModelEvaluator.compare_models(model_results)

        actual_arr = test.values
        pred_arrays = {}
        for mn, metrics in model_results.items():
            pred_arrays[mn] = metrics.get('predictions', [])

        pred_chart = ModelEvaluator.plot_predictions_comparison(
            actual_arr,
            pred_arrays,
            [str(d.date()) if hasattr(d, 'date') else str(d) for d in test.index],
        )

        result = {
            'family': family,
            'family_zh': FAMILY_ZH_MAP.get(family, family),
            'store_nbr': store_nbr,
            'forecast_days': forecast_days,
            'models': model_predictions,
            'evaluation': {
                **eval_results,
                'prediction_chart': pred_chart,
            },
        }
        TaskManager.complete(task_id, _sanitize_json(result))

    except Exception as e:
        logger.exception(f'Prediction task {task_id} failed')
        TaskManager.fail(task_id, str(e))


@app.route('/api/predict/progress')
def predict_progress():
    task_id = request.args.get('task_id')
    if not task_id:
        return _err(400, 'task_id 参数必填')
    task = TaskManager.get(task_id)
    if not task:
        return _err(404, f'任务不存在：{task_id}')
    return _ok({
        'task_id': task_id,
        'status': task['status'],
        'progress': task['progress'],
        'current_step': task['current_step'],
        'model_status': task['model_status'],
        'error': task['error'],
    })


@app.route('/api/predict/result')
def predict_result():
    task_id = request.args.get('task_id')
    if not task_id:
        return _err(400, 'task_id 参数必填')
    task = TaskManager.get(task_id)
    if not task:
        return _err(404, f'任务不存在：{task_id}')
    if task['status'] != 'done':
        return _err(400, '任务尚未完成')
    return _ok(task['result'])


@app.route('/api/predict/cancel', methods=['POST'])
def predict_cancel():
    body = request.get_json(silent=True) or {}
    task_id = body.get('task_id')
    if not task_id:
        return _err(400, 'task_id 参数必填')
    TaskManager.cancel(task_id)
    return _ok({'cancelled': True})


@app.route('/api/export/forecast')
def export_forecast():
    task_id = request.args.get('task_id')
    fmt = request.args.get('format', 'csv')
    if not task_id:
        return _err(400, 'task_id 参数必填')
    if fmt.lower() != 'csv':
        return _err(400, '当前仅支持 csv 导出')
    task = TaskManager.get(task_id)
    if not task or task['status'] != 'done':
        return _err(400, '任务尚未完成')

    result = task['result']
    family = result.get('family', 'unknown')
    store_nbr = result.get('store_nbr', 0)
    rows = []
    for model_name, pred in result.get('models', {}).items():
        dates = pred.get('dates', [])
        forecast = pred.get('forecast', [])
        lower = pred.get('lower_ci', [None] * len(dates))
        upper = pred.get('upper_ci', [None] * len(dates))
        for d, fc, lo, hi in zip(dates, forecast, lower, upper):
            rows.append({
                'date': d,
                'model': model_name,
                'forecast': fc,
                'lower_ci': lo,
                'upper_ci': hi,
            })

    df_out = pd.DataFrame(rows)
    today = datetime.now().strftime('%Y%m%d')
    filename = f'forecast_{family}_{store_nbr}_{today}.csv'
    buf = io.StringIO()
    df_out.to_csv(buf, index=False)
    buf.seek(0)
    return send_file(
        io.BytesIO(buf.getvalue().encode('utf-8-sig')),
        mimetype='text/csv',
        as_attachment=True,
        download_name=filename,
    )


@app.errorhandler(Exception)
def handle_error(e):
    code = getattr(e, 'code', 500)
    return _err(code, str(e))


if __name__ == '__main__':
    os.makedirs(DATA_PROCESSED_DIR, exist_ok=True)
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    app.run(debug=debug_mode, port=5000, host='0.0.0.0')
