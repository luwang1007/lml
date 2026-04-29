import math
import logging
from datetime import datetime

import numpy as np
import pandas as pd
from statsmodels.tsa.seasonal import STL

from config import COL_DATE, COL_STORE, COL_FAMILY, COL_SALES, COL_ONPROMO, FAMILY_ZH_MAP

logger = logging.getLogger(__name__)

_WEEKDAY_ZH = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
_MONTH_ZH   = [f'{i}月' for i in range(1, 13)]


def _safe(obj):
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return None if (math.isnan(obj) or math.isinf(obj)) else float(obj)
    if isinstance(obj, np.ndarray):
        return [_safe(v) for v in obj]
    return obj


def _ok(data):
    return {'success': True, 'data': data}


def _err(msg):
    return {'success': False, 'error': msg}


class DataAnalyzer:
    def __init__(self, df: pd.DataFrame):
        self._df = df.copy()
        self._df[COL_DATE] = pd.to_datetime(self._df[COL_DATE])
        self._daily_total = self._df.groupby(COL_DATE)[[COL_SALES]].sum()

    def get_overview_stats(self) -> dict:
        df = self._df
        total_sales    = float(df[COL_SALES].sum())
        n_days         = df[COL_DATE].dt.date.nunique()
        avg_daily      = total_sales / n_days if n_days else 0.0

        years = sorted(df[COL_DATE].dt.year.unique())
        yoy = None
        if len(years) >= 2:
            y_last = df[df[COL_DATE].dt.year == years[-1]][COL_SALES].sum()
            y_prev = df[df[COL_DATE].dt.year == years[-2]][COL_SALES].sum()
            if y_prev > 0:
                yoy = round((y_last - y_prev) / y_prev * 100, 2)

        by_family = df.groupby(COL_FAMILY)[COL_SALES].sum()
        best_fam  = by_family.idxmax()

        return _ok({
            'total_sales':     _safe(total_sales),
            'avg_daily_sales': _safe(avg_daily),
            'yoy_growth':      _safe(yoy),
            'best_family': {
                'name':    best_fam,
                'name_zh': FAMILY_ZH_MAP.get(best_fam, best_fam),
                'sales':   _safe(float(by_family[best_fam])),
            },
            'date_range': {
                'start': str(df[COL_DATE].min().date()),
                'end':   str(df[COL_DATE].max().date()),
                'days':  n_days,
            },
            'store_count':  int(df[COL_STORE].nunique()),
            'family_count': int(df[COL_FAMILY].nunique()),
        })

    def get_trend_chart(self, granularity: str = 'monthly',
                        family: str = 'all', store_nbr=0) -> dict:
        df = self._df.copy()

        if family != 'all':
            df = df[df[COL_FAMILY] == family]
        if store_nbr and int(store_nbr) != 0:
            df = df[df[COL_STORE] == int(store_nbr)]

        if df.empty:
            return _err('筛选后数据为空，请调整筛选条件')

        n_days = df[COL_DATE].dt.date.nunique()
        if granularity == 'daily' and n_days > 365:
            granularity = 'weekly'
            logger.info('daily 数据量 > 365 天，自动降级为 weekly')

        freq_map = {'daily': 'D', 'weekly': 'W', 'monthly': 'ME'}
        freq = freq_map.get(granularity, 'ME')

        grouped = df.groupby(pd.Grouper(key=COL_DATE, freq=freq))[COL_SALES].sum()

        if granularity == 'monthly':
            x_labels = [d.strftime('%Y-%m') for d in grouped.index]
        elif granularity == 'weekly':
            x_labels = [d.strftime('%Y-W%W') for d in grouped.index]
        else:
            x_labels = [d.strftime('%Y-%m-%d') for d in grouped.index]

        return _ok({
            'xAxis': x_labels,
            'series': [{'name': '销售量（件）', 'data': [_safe(v) for v in grouped.values]}],
        })

    def get_monthly_comparison(self) -> dict:
        df = self._df.copy()
        date_range_months = (df[COL_DATE].max().year - df[COL_DATE].min().year) * 12 + \
                            df[COL_DATE].max().month - df[COL_DATE].min().month
        if date_range_months < 13:
            return _ok({'months': _MONTH_ZH, 'series': [], 'message': '数据不足一年，无法做同比分析'})

        df['year']  = df[COL_DATE].dt.year
        df['month'] = df[COL_DATE].dt.month
        pivot = df.groupby(['year', 'month'])[COL_SALES].sum().unstack(level=0)

        series = []
        for yr in sorted(pivot.columns):
            row = pivot[yr]
            data = [_safe(row.get(m)) for m in range(1, 13)]
            series.append({'name': f'{yr}年', 'data': data})

        return _ok({'months': _MONTH_ZH, 'series': series})

    def get_category_pie(self) -> dict:
        by_fam = self._df.groupby(COL_FAMILY)[COL_SALES].sum()
        total  = float(by_fam.sum())
        series = [
            {'name': FAMILY_ZH_MAP.get(fam, fam), 'value': _safe(float(val))}
            for fam, val in by_fam.items()
        ]
        return _ok({'series': series, 'total': _safe(total)})

    def get_top_families(self, n: int = 10) -> dict:
        n = max(1, min(n, 33))
        by_fam = self._df.groupby(COL_FAMILY)[COL_SALES].sum().nlargest(n)
        families_zh = [FAMILY_ZH_MAP.get(f, f) for f in by_fam.index]
        sales       = [_safe(float(v)) for v in by_fam.values]

        promo_avg = []
        if COL_ONPROMO in self._df.columns:
            for fam in by_fam.index:
                avg = self._df[self._df[COL_FAMILY] == fam][COL_ONPROMO].mean()
                promo_avg.append(_safe(float(avg)))
        else:
            promo_avg = [None] * n

        return _ok({'families': families_zh, 'sales': sales, 'onpromotion_avg': promo_avg})

    def get_correlation_heatmap(self) -> dict:
        families = self._df[COL_FAMILY].unique()
        if len(families) < 2:
            return _err('品类数不足 2，无法计算相关性')

        pivot = (
            self._df.groupby([COL_DATE, COL_FAMILY])[COL_SALES].sum()
            .unstack(fill_value=0)
        )
        corr = pivot.corr()
        names_zh = [FAMILY_ZH_MAP.get(f, f) for f in corr.columns]
        matrix   = [[_safe(v) for v in row] for row in corr.values]
        return _ok({'products': names_zh, 'matrix': matrix})

    def get_weekday_pattern(self) -> dict:
        df = self._df.copy()
        df['weekday'] = df[COL_DATE].dt.dayofweek
        avg = df.groupby('weekday')[COL_SALES].mean().reindex(range(7), fill_value=0)
        return _ok({'days': _WEEKDAY_ZH, 'avg_sales': [_safe(float(v)) for v in avg.values]})

    def get_seasonal_decomposition(self, family: str = None,
                                   store_nbr=0, period: int = 7) -> dict:
        df = self._df.copy()
        if family and family != 'all':
            df = df[df[COL_FAMILY] == family]
        if store_nbr and int(store_nbr) != 0:
            df = df[df[COL_STORE] == int(store_nbr)]

        series = df.groupby(COL_DATE)[COL_SALES].sum().sort_index()

        if len(series) < 2 * period:
            return _err(f'序列长度不足，无法分解（需 ≥ {2 * period} 天）')
        if series.std() == 0:
            return _err('序列无变化（常数），无法分解')

        series = series.ffill().bfill().fillna(0)
        try:
            stl = STL(series, period=period, robust=True)
            res = stl.fit()
        except Exception as e:
            return _err(f'STL 分解失败：{e}')

        dates = [d.strftime('%Y-%m-%d') for d in series.index]
        return _ok({
            'dates':    dates,
            'observed': [_safe(v) for v in res.observed],
            'trend':    [_safe(v) for v in res.trend],
            'seasonal': [_safe(v) for v in res.seasonal],
            'residual': [_safe(v) for v in res.resid],
        })

    def get_promotion_effect(self, family: str = None) -> dict:
        if COL_ONPROMO not in self._df.columns:
            return _err('数据不含促销字段（onpromotion），无法分析促销效果')

        df = self._df.copy()
        if family and family != 'all':
            df = df[df[COL_FAMILY] == family]

        promo     = df[df[COL_ONPROMO] > 0][COL_SALES]
        non_promo = df[df[COL_ONPROMO] == 0][COL_SALES]
        promo_avg     = float(promo.mean()) if len(promo) else 0.0
        non_promo_avg = float(non_promo.mean()) if len(non_promo) else 0.0
        lift = (promo_avg / non_promo_avg) if non_promo_avg > 0 else None

        by_family = []
        for fam, grp in df.groupby(COL_FAMILY):
            p  = float(grp[grp[COL_ONPROMO] > 0][COL_SALES].mean() or 0)
            np_ = float(grp[grp[COL_ONPROMO] == 0][COL_SALES].mean() or 0)
            by_family.append({
                'name':          FAMILY_ZH_MAP.get(fam, fam),
                'promo_avg':     _safe(p),
                'non_promo_avg': _safe(np_),
                'lift':          _safe(p / np_ if np_ > 0 else None),
            })
        by_family.sort(key=lambda x: (x['lift'] or 0), reverse=True)

        return _ok({
            'promo_avg':     _safe(promo_avg),
            'non_promo_avg': _safe(non_promo_avg),
            'lift_ratio':    _safe(lift),
            'by_family':     by_family[:10],
        })

    def generate_analysis_report(self) -> dict:
        return {
            'generated_at': datetime.now().isoformat(),
            'overview':     self.get_overview_stats(),
            'trend':        self.get_trend_chart(granularity='monthly'),
            'monthly_cmp':  self.get_monthly_comparison(),
            'category_pie': self.get_category_pie(),
            'top_families': self.get_top_families(10),
            'correlation':  self.get_correlation_heatmap(),
            'weekday':      self.get_weekday_pattern(),
            'promo_effect': self.get_promotion_effect(),
        }
