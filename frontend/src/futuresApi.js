// API client แยกของ futures — ไม่แตะ src/api.js ของ spot เดิม
const BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

async function req(path, options = {}) {
  const res = await fetch(`${BASE}/api/futures${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  const text = await res.text()
  let data
  try { data = text ? JSON.parse(text) : null } catch { data = { detail: text } }
  if (!res.ok) throw new Error(data?.detail || `HTTP ${res.status}`)
  return data
}

const qs = (o) => new URLSearchParams(
  Object.entries(o).filter(([, v]) => v !== null && v !== undefined && v !== '')
).toString()

export const fapi = {
  account: () => req('/account'),
  market: (symbol) => req(`/market${symbol ? `?symbol=${encodeURIComponent(symbol)}` : ''}`),
  candles: (symbol, tf = '15m', limit = 200) => req(`/candles?${qs({ symbol, tf, limit })}`),
  preview: (p) => req(`/preview?${qs(p)}`),
  history: (limit = 50) => req(`/history?limit=${limit}`),
  stats: () => req('/stats'),

  order: (body) => req('/order', { method: 'POST', body: JSON.stringify(body) }),
  close: (symbol, portion = 1, note = '') =>
    req('/close', { method: 'POST', body: JSON.stringify({ symbol, portion, note }) }),
  closeAll: () => req('/close-all', { method: 'POST' }),
  leverage: (symbol, leverage) =>
    req('/leverage', { method: 'POST', body: JSON.stringify({ symbol, leverage }) }),
  reset: (balance) =>
    req('/reset', { method: 'POST', body: JSON.stringify({ balance, confirm: true }) }),
  botStatus: () => req('/bot-status'),
  setBotEnabled: (enabled) =>
    req('/bot-toggle', { method: 'POST', body: JSON.stringify({ enabled }) }),
}
