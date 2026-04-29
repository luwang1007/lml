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

const CHART_COLORS = ['#118DFF', '#12239E', '#E66C37', '#6B007B', '#E044A7', '#744EC2', '#D9B300', '#D64550'];

function formatNumber(value, digits = 0) {
  const number = Number(value || 0);
  return number.toLocaleString(undefined, { maximumFractionDigits: digits });
}

function baseChartOption(extra = {}) {
  return {
    color: CHART_COLORS,
    backgroundColor: 'transparent',
    textStyle: { color: '#605e5c', fontFamily: '"Segoe UI", "Microsoft YaHei", Arial, sans-serif' },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(255, 255, 255, 0.96)',
      borderColor: '#edebe9',
      borderWidth: 1,
      textStyle: { color: '#252423' },
      extraCssText: 'box-shadow: 0 3px 10px rgba(0,0,0,0.10);'
    },
    legend: { top: 0, itemWidth: 12, itemHeight: 8, textStyle: { color: '#605e5c', fontSize: 11 } },
    grid: { left: 42, right: 18, bottom: 38, top: 42, containLabel: true },
    xAxis: {
      axisLine: { lineStyle: { color: '#edebe9' } },
      axisTick: { show: false },
      axisLabel: { color: '#605e5c', fontSize: 11 }
    },
    yAxis: {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: '#605e5c', fontSize: 11 },
      splitLine: { lineStyle: { color: '#edebe9', type: 'dashed' } }
    },
    ...extra
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
