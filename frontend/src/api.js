const BASE = 'http://localhost:8000/api'
const get = (p) => fetch(`${BASE}${p}`).then(r => r.json())
const post = (p, body) => fetch(`${BASE}${p}`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
}).then(async r => { if (!r.ok) throw new Error((await r.json()).detail); return r.json() })

export const api = {
  assets: () => get('/assets'),
  analysis: (symbol) => get(`/analysis?symbol=${encodeURIComponent(symbol)}`),
  candles: (symbol, tf = '1h') => get(`/candles?symbol=${encodeURIComponent(symbol)}&timeframe=${tf}`),
  journal: () => get('/journal'),
  stats: () => get('/journal/stats'),
  bot: () => get('/bot'),
  getAuto: () => get('/auto'),
  getAutoStatus: () => get('/auto/status'),
  setAuto: (symbol, enabled) => post('/auto', { symbol, enabled }),
  openTrade: (b) => post('/journal/open', b),
  closeTrade: (b) => post('/journal/close', b),
}

// แยกฐาน/สกุลอ้างอิงจาก symbol ที่ต่อกันตรงๆ ไม่มีตัวคั่น (เช่น BTCTHB, ETHBTC)
const KNOWN_QUOTES = ['USDT', 'THB', 'BTC']
export function splitSymbol(symbol) {
  for (const q of KNOWN_QUOTES) {
    if (symbol.endsWith(q) && symbol.length > q.length) {
      return { base: symbol.slice(0, -q.length), quote: q }
    }
  }
  return { base: symbol, quote: '' }
}
