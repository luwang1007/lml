const FAMILY_ZH_MAP = {
  'AUTOMOTIVE':'汽车用品','BABY CARE':'婴儿用品','BEAUTY':'美妆',
  'BEVERAGES':'饮料','BOOKS':'图书','BREAD/BAKERY':'面包烘焙',
  'CELEBRATION':'节庆礼品','CLEANING':'清洁用品','DAIRY':'乳制品',
  'DELI':'熟食','EGGS':'蛋类','FROZEN FOODS':'冷冻食品',
  'GROCERY I':'杂货I','GROCERY II':'杂货II','HARDWARE':'五金',
  'HOME AND KITCHEN I':'家居厨具I','HOME AND KITCHEN II':'家居厨具II',
  'HOME APPLIANCES':'家电','HOME CARE':'家居护理','LADIESWEAR':'女装',
  'LAWN AND GARDEN':'园艺','LINGERIE':'内衣','LIQUOR,WINE,BEER':'酒水',
  'MAGAZINES':'杂志','MEATS':'肉类','PERSONAL CARE':'个人护理',
  'PET SUPPLIES':'宠物用品','PLAYERS AND ELECTRONICS':'电子产品',
  'POULTRY':'禽肉','PREPARED FOODS':'即食食品','PRODUCE':'生鲜',
  'SCHOOL AND OFFICE SUPPLIES':'文具办公','SEAFOOD':'海鲜'
};

const CHART_COLORS = ['#7CF9C8', '#FFB454', '#67B7FF', '#B08CFF', '#FF8F9A', '#6CE6FF', '#FFE066', '#3DDC97'];
const CHART_TEXT = '#F2FBF7';
const CHART_MUTED_TEXT = '#DCEBE5';
const CHART_SUBTLE_TEXT = '#708780';

function formatNumber(value, digits = 0) {
  const number = Number(value || 0);
  return number.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function hasOwn(obj, key) {
  return Object.prototype.hasOwnProperty.call(obj || {}, key);
}

function mergeTextStyle(base = {}, override = {}) {
  return { ...base, ...override };
}

function mergeLegend(base, override = {}) {
  const merged = {
    ...base,
    ...override,
    textStyle: mergeTextStyle(base.textStyle, override.textStyle)
  };
  if (hasOwn(override, 'bottom') && !hasOwn(override, 'top')) delete merged.top;
  if (hasOwn(override, 'top') && !hasOwn(override, 'bottom')) delete merged.bottom;
  return merged;
}

function mergeAxis(base, override) {
  if (!override) return base;
  if (Array.isArray(override)) return override.map(item => mergeAxis(base, item));

  const merged = { ...base, ...override };
  if (base.axisLine || override.axisLine) {
    merged.axisLine = { ...(base.axisLine || {}), ...(override.axisLine || {}) };
    if ((base.axisLine && base.axisLine.lineStyle) || (override.axisLine && override.axisLine.lineStyle)) {
      merged.axisLine.lineStyle = {
        ...((base.axisLine || {}).lineStyle || {}),
        ...((override.axisLine || {}).lineStyle || {})
      };
    }
  }
  if (base.axisTick || override.axisTick) {
    merged.axisTick = { ...(base.axisTick || {}), ...(override.axisTick || {}) };
  }
  if (base.axisLabel || override.axisLabel) {
    merged.axisLabel = mergeTextStyle(base.axisLabel, override.axisLabel);
  }
  if (base.nameTextStyle || override.nameTextStyle) {
    merged.nameTextStyle = mergeTextStyle(base.nameTextStyle, override.nameTextStyle);
  }
  if (base.splitLine || override.splitLine) {
    merged.splitLine = { ...(base.splitLine || {}), ...(override.splitLine || {}) };
    if ((base.splitLine && base.splitLine.lineStyle) || (override.splitLine && override.splitLine.lineStyle)) {
      merged.splitLine.lineStyle = {
        ...((base.splitLine || {}).lineStyle || {}),
        ...((override.splitLine || {}).lineStyle || {})
      };
    }
  }
  return merged;
}

function baseChartOption(extra = {}) {
  const base = {
    color: CHART_COLORS,
    backgroundColor: 'transparent',
    textStyle: { color: CHART_MUTED_TEXT, fontFamily: '"Microsoft YaHei UI", "HarmonyOS Sans SC", sans-serif' },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(4, 8, 15, 0.96)',
      borderColor: 'rgba(124, 249, 200, 0.3)',
      borderWidth: 1,
      textStyle: { color: CHART_TEXT },
      extraCssText: 'backdrop-filter: blur(12px); box-shadow: 0 16px 36px rgba(0,0,0,0.34); border-radius: 14px;'
    },
    legend: {
      top: 0,
      itemWidth: 12,
      itemHeight: 8,
      textStyle: { color: CHART_TEXT, fontSize: 12, fontWeight: 700 },
      inactiveColor: CHART_SUBTLE_TEXT,
      pageIconColor: '#7CF9C8',
      pageIconInactiveColor: CHART_SUBTLE_TEXT,
      pageTextStyle: { color: CHART_MUTED_TEXT }
    },
    grid: { left: 42, right: 18, bottom: 38, top: 42, containLabel: true },
    xAxis: {
      axisLine: { lineStyle: { color: 'rgba(255,255,255,0.14)' } },
      axisTick: { show: false },
      axisLabel: { color: CHART_MUTED_TEXT, fontSize: 12 },
      nameTextStyle: { color: CHART_MUTED_TEXT, fontSize: 12 }
    },
    yAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: CHART_MUTED_TEXT, fontSize: 12 },
      nameTextStyle: { color: CHART_MUTED_TEXT, fontSize: 12 },
      splitLine: { lineStyle: { color: 'rgba(255,255,255,0.10)', type: 'dashed' } }
    }
  };

  return {
    ...base,
    ...extra,
    textStyle: mergeTextStyle(base.textStyle, extra.textStyle),
    tooltip: {
      ...base.tooltip,
      ...(extra.tooltip || {}),
      textStyle: mergeTextStyle(base.tooltip.textStyle, extra.tooltip && extra.tooltip.textStyle)
    },
    legend: mergeLegend(base.legend, extra.legend),
    grid: { ...base.grid, ...(extra.grid || {}) },
    xAxis: mergeAxis(base.xAxis, extra.xAxis),
    yAxis: mergeAxis(base.yAxis, extra.yAxis)
  };
}

async function apiFetch(url, options = {}) {
  const resp = await fetch(url, options);
  const json = await resp.json();
  if (json.code !== 200) throw new Error(json.message || '请求失败');
  return json.data;
}

function showToast(type, message) {
  const container = document.getElementById('toast-container');
  const colorClass = type === 'success' ? 'bg-success' : (type === 'error' ? 'bg-danger' : 'bg-info');
  const toastHtml = `
    <div class="toast align-items-center text-white ${colorClass} border-0" role="alert" aria-live="assertive" aria-atomic="true">
      <div class="d-flex">
        <div class="toast-body">${message}</div>
        <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
      </div>
    </div>
  `;
  const div = document.createElement('div');
  div.innerHTML = toastHtml;
  const toastEl = div.querySelector('.toast');
  container.appendChild(toastEl);
  const toast = new bootstrap.Toast(toastEl, { delay: 4000 });
  toast.show();
  toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
}

function showLoading(text = '加载中...') {
  document.getElementById('global-loading').style.display = 'flex';
  document.getElementById('loading-text').textContent = text;
}

function hideLoading() {
  document.getElementById('global-loading').style.display = 'none';
}

function getSessionId() { return sessionStorage.getItem('session_id'); }
function setSessionId(id) { sessionStorage.setItem('session_id', id); }
function getTaskId() { return sessionStorage.getItem('task_id'); }
function setTaskId(id) { sessionStorage.setItem('task_id', id); }

const chartRegistry = [];
function registerChart(domId) {
  const dom = document.getElementById(domId);
  if (!dom) return null;
  const chart = echarts.init(dom);
  chartRegistry.push(chart);
  return chart;
}

window.addEventListener('resize', () => {
  chartRegistry.forEach(c => c.resize());
});

document.addEventListener('shown.bs.tab', () => {
  chartRegistry.forEach(c => c.resize());
});

document.addEventListener('DOMContentLoaded', () => {
  const currentPath = window.location.pathname || '/';
  document.querySelectorAll('.side-nav .nav-link').forEach(link => {
    const href = link.getAttribute('href');
    if (href === currentPath || (href !== '/' && currentPath.startsWith(href))) {
      link.classList.add('active');
    }
  });
});
