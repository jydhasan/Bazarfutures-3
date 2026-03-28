/**
 * BazarFutures — api.js v3
 * Matches new index.html element IDs exactly.
 * Fixes: chart click, contract creation, mobile layout bugs.
 */

const API_BASE = '/api';

/* ═══ AUTH STORE ═══════════════════════════════ */
const Auth = {
  tok:     () => localStorage.getItem('bf_tok'),
  setTok:  t  => localStorage.setItem('bf_tok', t),
  user:    () => { try { return JSON.parse(localStorage.getItem('bf_usr')); } catch { return null; } },
  setUser: u  => localStorage.setItem('bf_usr', JSON.stringify(u)),
  clear:   () => { localStorage.removeItem('bf_tok'); localStorage.removeItem('bf_usr'); },
  in:      () => !!localStorage.getItem('bf_tok'),
  admin:   () => Auth.user()?.role === 'admin',
};

/* ═══ NORMALIZE product from API ═══════════════ */
function norm(p) {
  const key  = 'pp_' + p.id;
  const cur  = parseFloat(p.current_price);
  const prev = parseFloat(sessionStorage.getItem(key) || 0);
  sessionStorage.setItem(key, cur);
  return {
    id: p.id, name: p.name_bn, en: p.name_en,
    unit: p.unit, cat: p.category,
    price: cur,
    oldPrice: (prev && prev !== cur) ? prev : null,
    active: p.is_active,
    url: p.chaldal_url,
    _r: p,
  };
}

/* ═══ BASE FETCH ════════════════════════════════ */
async function api(path, opts = {}) {
  const h = { 'Content-Type': 'application/json', ...opts.headers };
  const t = Auth.tok();
  if (t) h['Authorization'] = 'Bearer ' + t;
  let r;
  try {
    r = await fetch(API_BASE + path, { ...opts, headers: h });
  } catch {
    showToast('সার্ভার সংযোগ ব্যর্থ', 'error'); return null;
  }
  if (r.status === 401) {
    Auth.clear(); updateNav();
    showToast('সেশন শেষ — আবার লগইন করুন', 'error');
    showPage('login'); return null;
  }
  const d = await r.json().catch(() => null);
  if (!r.ok) {
    const m = Array.isArray(d?.detail) ? d.detail.map(x => x.msg).join(', ') : (d?.detail || 'ত্রুটি হয়েছে');
    showToast(m, 'error'); return null;
  }
  return d;
}

/* ═══ API MODULES ═══════════════════════════════ */
const A = {
  // Auth
  register: (name,email,pass) => api('/auth/register', {method:'POST', body:JSON.stringify({name,email,password:pass})}),
  login:    async (email,pass) => {
    const d = await api('/auth/login', {method:'POST', body:JSON.stringify({email,password:pass})});
    if (d?.access_token) { Auth.setTok(d.access_token); const me = await api('/auth/me'); if (me) Auth.setUser(me); return true; }
    return false;
  },
  me: () => api('/auth/me'),

  // Products
  products:   (cat,q) => { const p=new URLSearchParams(); if(cat&&cat!=='all')p.set('category',cat); if(q)p.set('search',q); return api('/products'+(p.toString()?'?'+p:'')); },
  productsRaw: () => api('/products'),
  history:    (id,days) => api(`/products/${id}/history?days=${days}`),
  updateProd: (id,body) => api(`/products/${id}`, {method:'PATCH', body:JSON.stringify(body)}),
  bulkPrice:  updates  => api('/products/bulk-price-update', {method:'POST', body:JSON.stringify({updates})}),
  addProduct: body     => api('/products', {method:'POST', body:JSON.stringify(body)}),

  // Contracts
  contracts:    status => api('/contracts/public' + (status ? '?status='+status : '')),
  myContracts:  ()     => api('/contracts?my=true'),
  contract:     id     => api('/contracts/'+id),
  createCont:   body   => api('/contracts', {method:'POST', body:JSON.stringify(body)}),
  placeBid:     (cid,price,msg) => api(`/contracts/${cid}/bids`, {method:'POST', body:JSON.stringify({bid_price:price,message:msg})}),
  acceptBid:    (cid,bid) => api(`/contracts/${cid}/bids/${bid}/accept`, {method:'POST'}),
  sendProposal: (cid,body)=> api(`/contracts/${cid}/proposals`, {method:'POST', body:JSON.stringify(body)}),

  // Wallet
  balance:  () => api('/wallet/balance'),
  txns:     () => api('/wallet/transactions'),
  deposit:  b  => api('/wallet/deposit',  {method:'POST', body:JSON.stringify(b)}),
  withdraw: b  => api('/wallet/withdraw', {method:'POST', body:JSON.stringify(b)}),
  pending:  () => api('/wallet/admin/pending'),
  approveDep: id => api(`/wallet/admin/approve-deposit/${id}`,    {method:'POST'}),
  approveWd:  id => api(`/wallet/admin/approve-withdrawal/${id}`, {method:'POST'}),
  rejectTxn:  id => api(`/wallet/admin/reject/${id}`,             {method:'POST'}),

  // Admin
  stats:      () => api('/admin/stats'),
  users:      () => api('/admin/users'),
  allConts:   () => api('/admin/contracts'),
  toggleUser: id => api(`/admin/users/${id}/toggle`, {method:'PATCH'}),
  scrape:     () => api('/admin/trigger-scrape',     {method:'POST'}),
  previewScrape: () => api('/admin/preview-scrape',  {method:'POST'}),
  settle:     () => api('/admin/trigger-settlement', {method:'POST'}),
  fetchPreview: () => api('/admin/fetch-preview'),   // GET — no DB write
};

/* ═══ CACHE ═════════════════════════════════════ */
let _prods = [], _prodMap = {};

async function loadProds(cat, q) {
  const raw = await A.products(cat, q);
  if (!raw) return null;
  _prods   = raw.map(norm);
  _prodMap = {};
  _prods.forEach(p => _prodMap[p.id] = p);
  return _prods;
}

/* ═══ NAV ═══════════════════════════════════════ */
function updateNav() {
  const loggedIn = Auth.in();
  const user     = Auth.user();

  document.getElementById('loginBtn').style.display  = loggedIn ? 'none' : '';
  document.getElementById('regBtn').style.display    = loggedIn ? 'none' : '';
  document.getElementById('dashBtn').style.display   = loggedIn ? '' : 'none';
  document.getElementById('adminBtn').style.display  = (loggedIn && user?.role==='admin') ? '' : 'none';

  if (loggedIn && user) {
    const n = user.name.split(' ')[0];
    document.getElementById('dashBtn').textContent = '👤 ' + n;
  }

  // Update home page stats if admin
  if (loggedIn && user?.role === 'admin') {
    A.stats().then(s => {
      if (!s) return;
      setEl('hs-products',  s.total_products);
      setEl('hs-contracts', s.open_contracts + s.matched_contracts);
      setEl('hs-users',     s.total_users);
    });
  }
}

function setEl(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val ?? '—';
}

/* ═══ TICKER ════════════════════════════════════ */
function buildTicker(prods) {
  const track = document.getElementById('tickerTrack');
  if (!track) return;
  const items = prods.slice(0, 18).map(p => {
    const chg  = p.oldPrice ? p.price - p.oldPrice : 0;
    const cls  = chg < 0 ? 'dn' : chg > 0 ? 'up' : '';
    const icon = getProdIcon(p.name);
    return `<div class="tick-item"><span>${icon} ${p.name}</span><span class="tp">৳${p.price}</span>${chg!==0?`<span class="${cls}">${chg>0?'+':''}${chg.toFixed(0)}</span>`:''}</div>`;
  }).join('');
  track.innerHTML = items + items;
}

/* ═══ PRODUCT ICON MAP ══════════════════════════ */
const PROD_ICONS = {
  // সবজি
  'আলু': '🥔', 'লাল আলু': '🥔', 'বড় আলু': '🥔', 'মিষ্টি আলু': '🍠',
  'টমেটো': '🍅', 'লাল টমেটো': '🍅',
  'ফুলকপি': '🥦', 'বাঁধাকপি': '🥬',
  'গাজর': '🥕', 'শসা': '🥒',
  'পেঁয়াজ': '🧅', 'রসুন': '🧄',
  'কাঁচা মরিচ': '🌶️', 'শুকনো মরিচ': '🌶️',
  'লাল শাক': '🥬', 'পালং শাক': '🥬',
  'ধনিয়া পাতা': '🌿', 'করলা': '🥒',
  'বেগুন': '🍆', 'কুমড়া': '🎃',
  'আদা': '🫚', 'ক্যাপসিকাম': '🫑', 'শিম': '🫘',
  // ফল
  'কলা': '🍌', 'পেয়ারা': '🍐', 'লেবু': '🍋', 'মাল্টা': '🍊',
  'আঙুর': '🍇', 'পেঁপে': '🍈', 'আম': '🥭', 'আপেল': '🍎',
  // ডাল/চাল
  'চাল': '🌾', 'আটা': '🌾', 'ময়দা': '🌾',
  'ডাল': '🫘', 'ছোলা': '🫘', 'মুগ': '🫘', 'মসুর': '🫘',
  'চিড়া': '🌾', 'মুড়ি': '🌾',
  // মশলা / তেল
  'সরিষার তেল': '🫙', 'জিরা': '✨', 'হলুদ': '✨',
  'দারুচিনি': '🪵', 'তেজপাতা': '🌿', 'লবঙ্গ': '🌰',
  'কিশমিশ': '🍇', 'মশলা': '🌶️',
  // ডেইরি
  'দুধ': '🥛', 'দই': '🥛', 'মিল্ক': '🥛',
  // অন্যান্য
  'ডিম': '🥚', 'চিনি': '🍬', 'লবণ': '🧂',
  'চা': '🍵', 'সেমাই': '🍜',
  'সাবান': '🧼', 'টিস্যু': '🧻', 'ন্যাপকিন': '🧻',
  'ডিটারজেন্ট': '🧴', 'ওয়াশিং': '🧴',
};

function getProdIcon(name) {
  // Try exact match first
  for (const [key, icon] of Object.entries(PROD_ICONS)) {
    if (name.includes(key)) return icon;
  }
  // Category fallback
  return '📦';
}

function getCatIcon(cat) {
  const map = {
    'সবজি':    '🥬',
    'ফল':      '🍌',
    'ডাল/চাল': '🌾',
    'মশলা':    '🌶️',
    'ডেইরি':   '🥛',
    'অন্যান্য': '📦',
  };
  return map[cat] || '📦';
}

/* ═══ PRICE GRID ════════════════════════════════ */
function renderGrid(data) {
  const grid = document.getElementById('priceGrid');
  if (!grid) return;
  let list = data || _prods;
  if (activeFilter && activeFilter !== 'all') list = list.filter(p => p.cat === activeFilter);
  if (searchTerm) {
    const q = searchTerm.toLowerCase();
    list = list.filter(p => p.name.includes(searchTerm) || (p.en||'').toLowerCase().includes(q));
  }
  if (!list.length) {
    grid.innerHTML = '<div class="empty-state">কোনো পণ্য পাওয়া যায়নি</div>';
    return;
  }
  grid.innerHTML = list.map(p => {
    const chg  = p.oldPrice ? p.price - p.oldPrice : 0;
    const cls  = chg < 0 ? 'up' : chg > 0 ? 'dn' : 'flat';
    const sign = chg > 0 ? '+' : '';
    const pct  = p.oldPrice ? Math.abs(Math.round(chg/p.oldPrice*100)) : 0;
    const icon = getProdIcon(p.name);
    return `<div class="price-card" onclick="">
      <div style="font-size:1.8rem;line-height:1;margin-bottom:6px">${icon}</div>
      <div class="pc-name">${p.name}</div>
      <div class="pc-unit">${p.unit} · ${getCatIcon(p.cat)} ${p.cat}</div>
      <div class="pc-price">৳${p.price} <small>/ ${p.unit}</small></div>
      <div class="pc-chg ${cls}">${p.oldPrice ? sign+'৳'+Math.abs(chg).toFixed(0)+' ('+pct+'%)' : '— আজকের দাম'}</div>
      <div class="pc-actions">
        <button class="btn btn-ghost btn-sm" onclick="event.stopPropagation();goChart(${p.id})" title="দামের ইতিহাস">📈 চার্ট</button>
        <button class="btn btn-solid btn-sm" onclick="event.stopPropagation();goCreate(${p.id},'${p.name.replace(/'/g,"\\'")}',${p.price})" title="কন্ট্র্যাক্ট তৈরি">+ চুক্তি</button>
      </div>
    </div>`;
  }).join('');
}

function goChart(productId) {
  _chartProductId = productId;
  showPage('history');
  loadHistory();
}

function goCreate(productId, name, price) {
  if (!Auth.in()) { showToast('কন্ট্র্যাক্ট তৈরিতে লগইন করুন', 'error'); showPage('login'); return; }
  openModal('createModal');
  setTimeout(() => {
    const sel = document.getElementById('cc-product');
    const opt = Array.from(sel.options).find(o => +o.dataset.pid === productId);
    if (opt) { sel.value = opt.value; }
    document.getElementById('cc-price').value = price;
    calcSecurity();
  }, 180);
}

/* Override filter/search stubs */
window.filterCat = function(cat, btn) {
  activeFilter = cat;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderGrid(_prods);
};
window.filterSearch = function(q) { searchTerm = q; renderGrid(_prods); };

/* ═══ TOP MOVERS (home page) ════════════════════ */
function renderMovers(prods) {
  const el = document.getElementById('topMovers');
  if (!el) return;
  const movers  = prods.filter(p => p.oldPrice).slice(0, 6);
  const display = movers.length ? movers : prods.slice(0, 6);
  el.innerHTML = display.map(p => {
    const chg  = p.oldPrice ? p.price - p.oldPrice : 0;
    const pct  = p.oldPrice ? Math.round(chg/p.oldPrice*100) : 0;
    const cls  = chg < 0 ? 'dn' : chg > 0 ? 'up' : 'flat';
    const icon = getProdIcon(p.name);
    return `<div class="price-card">
      <div style="font-size:1.8rem;line-height:1;margin-bottom:6px">${icon}</div>
      <div class="pc-name">${p.name}</div>
      <div class="pc-unit">${p.unit}</div>
      <div class="pc-price">৳${p.price}</div>
      <div class="pc-chg ${cls}">${chg!==0?(chg>0?'↑':'↓')+' ৳'+Math.abs(chg)+' ('+pct+'%)':'— আজকের রেট'}</div>
    </div>`;
  }).join('');
}

/* ═══ LOGOUT ════════════════════════════════════ */
window.doLogout = function() {
  Auth.clear();
  updateNav();
  showPage('home');
  showToast('✅ সফলভাবে লগআউট হয়েছেন', 'success');
};

/* ═══ CONTRACTS ═════════════════════════════════ */
function renderContracts(list) {
  const el = document.getElementById('contractList');
  if (!el) return;
  if (!list || !list.length) { el.innerHTML = '<div class="empty-state">কোনো কন্ট্র্যাক্ট নেই</div>'; return; }
  el.innerHTML = list.map(c => {
    const prod  = _prodMap[c.product_id];
    const name  = prod ? prod.name : 'পণ্য #' + c.product_id;
    const unit  = prod ? prod.unit : 'ইউনিট';
    const cur   = prod ? prod.price : 0;
    const qty   = parseFloat(c.quantity);
    const cprice= parseFloat(c.contract_price);
    const sec   = parseFloat(c.security_amount);
    const diff  = cprice - cur;
    const gain  = diff * qty;
    const isOpen = c.status === 'open';
    const sBadge = isOpen ? 'bg-green' : c.status === 'matched' ? 'bg-amber' : 'bg-gray';
    const sTxt   = isOpen ? 'বিড খোলা' : c.status === 'matched' ? 'ম্যাচড' : c.status === 'settled' ? 'নিষ্পত্তি' : c.status;
    return `<div class="cc">
      <div class="cc-top">
        <div class="cc-head">
          <div>
            <div class="cc-prod">${name} — ${qty} ${unit}</div>
            <div class="cc-meta">#${c.contract_code} · Seller #${c.seller_id}</div>
          </div>
          <div class="cc-badges">
            <span class="badge ${sBadge}">${sTxt}</span>
            ${cur ? `<span class="badge ${gain>=0?'bg-green':'bg-red'}">সম্ভাব্য ${gain>=0?'লাভ':'ক্ষতি'}: ৳${Math.abs(gain).toFixed(0)}</span>` : ''}
          </div>
        </div>
        <div class="cc-grid">
          <div class="cc-stat"><label>চুক্তির দাম</label><div class="v">৳${cprice}/${unit}</div></div>
          <div class="cc-stat"><label>বাজার দাম</label><div class="v">${cur?'৳'+cur:'—'}</div></div>
          <div class="cc-stat"><label>মোট মূল্য</label><div class="v">৳${parseFloat(c.total_value).toFixed(0)}</div></div>
          <div class="cc-stat"><label>জামানত ১৫%</label><div class="v text-primary">৳${sec.toFixed(0)}</div></div>
          <div class="cc-stat"><label>ম্যাচিউরিটি</label><div class="v">${c.maturity_date}</div></div>
          <div class="cc-stat"><label>ধরন</label><div class="v">${c.contract_type==='sell'?'SELL':'BUY'}</div></div>
        </div>
      </div>
      <div class="cc-foot">
        ${isOpen ? `
          <button class="btn btn-solid btn-sm" onclick="openBidModal(${c.id},'${c.contract_code}',${cprice},${qty})">🏷️ বিড করুন</button>
          <button class="btn btn-ghost btn-sm" onclick="openBidModal(${c.id},'${c.contract_code}',${cprice},${qty},true)">📩 প্রপোজাল</button>
        ` : `<span class="badge ${sBadge}">${sTxt} — বিড বন্ধ</span>`}
      </div>
    </div>`;
  }).join('');
}

window.switchTab = async function(status, btn) {
  document.querySelectorAll('.ctab').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  if (status === 'my') {
    if (!Auth.in()) { showToast('লগইন করুন', 'error'); return; }
    const d = await A.myContracts();
    renderContracts(d);
  } else {
    const d = await A.contracts(status);
    renderContracts(d);
  }
};

/* ═══ BID / PROPOSAL MODAL ══════════════════════ */
let _bidContractId = null, _isProposal = false;

window.openBidModal = async function(cid, code, price, qty, isProposal=false) {
  if (!Auth.in()) { showToast('লগইন করুন', 'error'); showPage('login'); return; }
  _bidContractId = cid; _isProposal = isProposal;
  document.getElementById('bidModalTitle').textContent = (isProposal ? '📩 প্রপোজাল — #' : 'বিড করুন — #') + code;
  document.getElementById('bid-price').value = price;
  document.getElementById('bid-qty').value   = qty;
  document.getElementById('bid-date').value  = '';
  document.getElementById('bid-msg').value   = '';

  const bidsEl = document.getElementById('existingBids');
  bidsEl.innerHTML = '<div style="color:var(--text-dim);font-size:0.8rem">লোড হচ্ছে...</div>';

  const detail = await A.contract(cid);
  if (detail?.bids?.length) {
    bidsEl.innerHTML = detail.bids.map(b => `<div class="bid-item">
      <div><div style="font-size:0.84rem">User #${b.bidder_id}</div><div class="bid-time">${new Date(b.created_at).toLocaleDateString('bn-BD')}</div></div>
      <div class="bid-price">৳${b.bid_price}</div>
      <span class="badge ${b.status==='pending'?'bg-amber':b.status==='accepted'?'bg-green':'bg-gray'}">${b.status}</span>
    </div>`).join('');
  } else {
    bidsEl.innerHTML = '<div style="color:var(--text-dim);font-size:0.8rem">এখনো কোনো বিড নেই</div>';
  }
  openModal('bidModal');
};

window.submitBid = async function() {
  if (!_bidContractId) return;
  const price = parseFloat(document.getElementById('bid-price').value);
  const msg   = document.getElementById('bid-msg').value;
  if (!price || price <= 0) { showToast('সঠিক দাম দিন', 'error'); return; }
  const r = await A.placeBid(_bidContractId, price, msg);
  if (r) { showToast('✅ বিড জমা হয়েছে!', 'success'); closeModal('bidModal'); reloadContracts(); }
};

window.submitProposal = async function() {
  if (!_bidContractId) return;
  const price = parseFloat(document.getElementById('bid-price').value);
  const qty   = parseFloat(document.getElementById('bid-qty').value) || null;
  const date  = document.getElementById('bid-date').value || null;
  const msg   = document.getElementById('bid-msg').value || null;
  if (!price || price <= 0) { showToast('সঠিক দাম দিন', 'error'); return; }
  const body  = { proposed_price: price, ...(qty?{proposed_qty:qty}:{}), ...(date?{proposed_date:date}:{}), ...(msg?{message:msg}:{}) };
  const r     = await A.sendProposal(_bidContractId, body);
  if (r) { showToast('📩 প্রপোজাল পাঠানো হয়েছে!', 'success'); closeModal('bidModal'); }
};

async function reloadContracts() {
  const d = await A.contracts('open'); renderContracts(d);
}

/* ═══ CREATE CONTRACT ═══════════════════════════ */
window.populateProductDropdown = async function() {
  const sel = document.getElementById('cc-product');
  if (!sel) return;
  sel.innerHTML = '<option value="">পণ্য বেছে নিন</option>';
  const prods = _prods.length ? _prods : await loadProds();
  if (!prods) return;
  prods.forEach(p => {
    const opt = new Option(`${p.name} — ৳${p.price}/${p.unit}`, p.id);
    opt.dataset.pid = p.id;
    opt.dataset.price = p.price;
    sel.appendChild(opt);
  });
};

window.submitCreateContract = async function() {
  if (!Auth.in()) { showToast('লগইন করুন', 'error'); return; }
  const sel    = document.getElementById('cc-product');
  const prodId = parseInt(sel.value);
  const qty    = parseFloat(document.getElementById('cc-qty').value);
  const price  = parseFloat(document.getElementById('cc-price').value);
  const date   = document.getElementById('cc-date').value;
  const type   = document.getElementById('cc-type').value;
  const terms  = document.getElementById('cc-terms').value || null;

  if (!prodId)         { showToast('পণ্য বেছে নিন', 'error'); return; }
  if (!qty || qty<=0)  { showToast('পরিমাণ দিন', 'error'); return; }
  if (!price||price<=0){ showToast('চুক্তির দাম দিন', 'error'); return; }
  if (!date)           { showToast('তারিখ দিন', 'error'); return; }
  if (new Date(date) <= new Date()) { showToast('ভবিষ্যতের তারিখ দিন', 'error'); return; }

  const r = await A.createCont({
    product_id: prodId, contract_type: type,
    quantity: qty, contract_price: price,
    maturity_date: date, ...(terms?{terms}:{}),
  });
  if (r) {
    showToast(`✅ কন্ট্র্যাক্ট #${r.contract_code} তৈরি হয়েছে!`, 'success');
    closeModal('createModal');
    showPage('contracts');
    const d = await A.contracts('open'); renderContracts(d);
  }
};

/* ═══ HISTORY / CHART ═══════════════════════════ */
let _chartProductId = null, _chartRange = 7;

async function loadHistory() {
  const sel   = document.getElementById('chartProductSel');
  const prods = _prods.length ? _prods : await loadProds();
  if (!prods || !sel) return;

  // Populate select
  if (sel.options.length <= 1 || sel.options[0].value === '') {
    sel.innerHTML = prods.map(p =>
      `<option value="${p.id}" ${p.id===_chartProductId?'selected':''}>${p.name} — ${p.unit}</option>`
    ).join('');
  }

  if (!_chartProductId) _chartProductId = prods[0]?.id;
  if (_chartProductId) sel.value = _chartProductId;

  await drawChartForProduct(_chartProductId);
}

window.onChartProductChange = async function() {
  const sel = document.getElementById('chartProductSel');
  _chartProductId = parseInt(sel.value);
  await drawChartForProduct(_chartProductId);
};

window.setRange = async function(days, btn) {
  document.querySelectorAll('.rng-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  _chartRange = days;
  await drawChartForProduct(_chartProductId);
};

async function drawChartForProduct(productId) {
  if (!productId) return;
  const prod    = _prodMap[productId];
  const history = await A.history(productId, _chartRange);
  const name    = prod ? prod.name : 'পণ্য #' + productId;

  setEl('chartTitle', name);

  if (!history || !history.length) {
    ['cs-cur','cs-hi','cs-lo','cs-avg','cs-chg'].forEach(id => setEl(id, '—'));
    setEl('cs-cur', prod ? '৳'+prod.price : '—');
    setEl('cs-chg', 'ইতিহাস তৈরি হচ্ছে...');
    drawEmptyChart();
    return;
  }

  const prices = history.map(h => parseFloat(h.price));
  const labels = history.map(h => {
    const d = new Date(h.recorded_at);
    return `${d.getDate()}/${d.getMonth()+1}`;
  });

  const cur  = prices[prices.length-1];
  const high = Math.max(...prices), low = Math.min(...prices);
  const avg  = prices.reduce((a,b) => a+b, 0) / prices.length;
  const chg  = cur - prices[0];
  const pct  = prices[0] ? Math.round(chg/prices[0]*100) : 0;

  setEl('cs-cur', '৳'+cur);
  setEl('cs-hi',  '৳'+high);
  setEl('cs-lo',  '৳'+low);
  setEl('cs-avg', '৳'+avg.toFixed(1));

  const chgEl = document.getElementById('cs-chg');
  if (chgEl) {
    chgEl.textContent  = `${chg>=0?'+':''}৳${chg.toFixed(0)} (${pct}%)`;
    chgEl.className    = 'cv ' + (chg >= 0 ? 'text-green' : 'text-red');
  }

  paintChart(prices, labels);
}

function drawEmptyChart() {
  const canvas = document.getElementById('priceChart');
  if (!canvas) return;
  canvas.width  = canvas.offsetWidth || 600;
  canvas.height = canvas.offsetHeight || 220;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0,0,canvas.width,canvas.height);
  ctx.fillStyle = 'rgba(124,96,64,0.4)';
  ctx.font = '14px Hind Siliguri,sans-serif';
  ctx.textAlign = 'center';
  ctx.fillText('ডেটা লোড হলে চার্ট দেখাবে', canvas.width/2, canvas.height/2);
}

function paintChart(prices, labels) {
  const canvas = document.getElementById('priceChart');
  if (!canvas) return;
  const parent = canvas.parentElement;
  canvas.width  = parent.offsetWidth  || 600;
  canvas.height = parent.offsetHeight || 220;

  const ctx = canvas.getContext('2d');
  const W=canvas.width, H=canvas.height;
  const pL=50, pR=16, pT=16, pB=36;
  const cW=W-pL-pR, cH=H-pT-pB, n=prices.length;
  const minP=Math.min(...prices)-5, maxP=Math.max(...prices)+5;

  ctx.clearRect(0,0,W,H);

  // Grid
  ctx.strokeStyle='rgba(245,158,11,0.08)'; ctx.lineWidth=1;
  for(let i=0;i<=4;i++){
    const y=pT+(cH/4)*i, v=Math.round(maxP-(maxP-minP)*(i/4));
    ctx.beginPath(); ctx.moveTo(pL,y); ctx.lineTo(W-pR,y); ctx.stroke();
    ctx.fillStyle='rgba(124,96,64,0.7)'; ctx.font='10px Space Mono,monospace';
    ctx.textAlign='right'; ctx.fillText('৳'+v, pL-5, y+4);
  }

  const xOf = i => pL + (n>1 ? cW/(n-1)*i : cW/2);
  const yOf = p => pT + cH - (p-minP)/(maxP-minP)*cH;

  // Area
  const g=ctx.createLinearGradient(0,pT,0,H-pB);
  g.addColorStop(0,'rgba(245,158,11,0.18)'); g.addColorStop(1,'rgba(245,158,11,0)');
  ctx.beginPath();
  prices.forEach((p,i) => i===0 ? ctx.moveTo(xOf(i),yOf(p)) : ctx.lineTo(xOf(i),yOf(p)));
  ctx.lineTo(xOf(n-1),H-pB); ctx.lineTo(pL,H-pB); ctx.closePath();
  ctx.fillStyle=g; ctx.fill();

  // Line
  ctx.beginPath(); ctx.strokeStyle='#f59e0b'; ctx.lineWidth=2.5;
  ctx.lineJoin='round'; ctx.lineCap='round';
  prices.forEach((p,i) => i===0 ? ctx.moveTo(xOf(i),yOf(p)) : ctx.lineTo(xOf(i),yOf(p)));
  ctx.stroke();

  // Dots + labels
  const step = Math.max(1, Math.floor(n/6));
  prices.forEach((p,i) => {
    if (i%step!==0 && i!==n-1) return;
    const x=xOf(i), y=yOf(p);
    ctx.beginPath(); ctx.arc(x,y,4,0,Math.PI*2);
    ctx.fillStyle='#f59e0b'; ctx.fill();
    ctx.strokeStyle='#1a1208'; ctx.lineWidth=2; ctx.stroke();
    ctx.fillStyle='rgba(124,96,64,0.8)'; ctx.font='10px Hind Siliguri,sans-serif';
    ctx.textAlign='center'; ctx.fillText(labels[i]||'', x, H-pB+14);
  });
}

/* ═══ DASHBOARD ═════════════════════════════════ */
async function loadDashboard() {
  if (!Auth.in()) return;
  const [me, bal, txns, myCont] = await Promise.all([
    A.me(), A.balance(), A.txns(), A.myContracts()
  ]);

  if (me) { Auth.setUser(me); updateNav(); setEl('dashName', me.name); setEl('dashEmail', me.email); }
  if (bal) {
    setEl('dashBal',    '৳' + parseFloat(bal.balance).toLocaleString());
    setEl('dashFrozen', bal.frozen_balance > 0 ? '🔒 ৳'+parseFloat(bal.frozen_balance).toLocaleString()+' জামানত' : '');
  }

  // Transactions
  const txEl = document.getElementById('txnList');
  if (txEl && txns) {
    const lbl = { deposit:'🟢 জমা', withdrawal:'↑ উত্তোলন', security_lock:'🔒 জামানত', security_release:'🔓 ছাড়', settlement_gain:'🟢 লাভ', settlement_loss:'🔴 লোকসান', commission:'💸 কমিশন' };
    const cr  = t => ['deposit','security_release','settlement_gain'].includes(t);
    txEl.innerHTML = txns.length ? txns.slice(0,15).map(t => `<div class="txn-item">
      <div><div class="txn-type">${lbl[t.txn_type]||t.txn_type}</div>
      <div class="txn-date">${new Date(t.created_at).toLocaleDateString('bn-BD')} · <span class="badge ${t.status==='completed'?'bg-green':t.status==='pending'?'bg-amber':'bg-gray'}" style="font-size:0.68rem;padding:2px 8px">${t.status}</span></div></div>
      <div class="txn-amt ${cr(t.txn_type)?'cr':'dr'}">${cr(t.txn_type)?'+':'-'}৳${parseFloat(t.amount).toLocaleString()}</div>
    </div>`).join('')
    : '<div class="empty-state">কোনো লেনদেন নেই</div>';
  }

  // My contracts
  const mcEl = document.getElementById('myContracts');
  if (mcEl && myCont) {
    mcEl.innerHTML = myCont.length ? myCont.map(c => `<div class="bid-item" style="margin-bottom:8px">
      <div><div style="font-size:0.86rem;font-weight:600">#${c.contract_code} — ${c.quantity} ইউনিট @ ৳${c.contract_price}</div>
      <div class="bid-time">ম্যাচিউর: ${c.maturity_date} · জামানত: ৳${parseFloat(c.security_amount).toFixed(0)}</div></div>
      <span class="badge ${c.status==='open'?'bg-green':c.status==='matched'?'bg-amber':'bg-gray'}">${c.status==='open'?'খোলা':c.status==='matched'?'ম্যাচড':c.status==='settled'?'নিষ্পত্তি':c.status}</span>
    </div>`).join('')
    : '<div class="empty-state">কোনো কন্ট্র্যাক্ট নেই<br><button class="btn btn-solid btn-sm" style="margin-top:12px" onclick="openModal(\'createModal\')">+ নতুন কন্ট্র্যাক্ট</button></div>';
  }
}

/* ═══ WALLET FORMS ══════════════════════════════ */
window.submitDeposit = async function() {
  const amount = parseFloat(document.getElementById('dep-amount')?.value);
  const pm     = document.getElementById('dep-pm')?.value || 'bkash';
  const acc    = document.getElementById('dep-acc')?.value?.trim();
  const txnId  = document.getElementById('dep-txn')?.value?.trim();
  if (!amount||amount<500) { showToast('ন্যূনতম ৳৫০০','error'); return; }
  if (!acc||acc.length<10) { showToast('সঠিক নম্বর দিন','error'); return; }
  if (!txnId||txnId.length<5) { showToast('TrxID দিন','error'); return; }
  const r = await A.deposit({amount, payment_method:pm, account_number:acc, external_txn_id:txnId});
  if (r) { showToast('✅ জমার আবেদন পাঠানো হয়েছে','success'); closeModal('depositModal'); }
};

window.submitWithdraw = async function() {
  const amount = parseFloat(document.getElementById('wd-amount')?.value);
  const pm     = document.getElementById('wd-pm')?.value || 'bkash';
  const acc    = document.getElementById('wd-acc')?.value?.trim();
  if (!amount||amount<200) { showToast('ন্যূনতম ৳২০০','error'); return; }
  if (!acc||acc.length<10) { showToast('সঠিক নম্বর দিন','error'); return; }
  const r = await A.withdraw({amount, payment_method:pm, account_number:acc});
  if (r) { showToast('✅ উইথড্র আবেদন জমা','success'); closeModal('withdrawModal'); loadDashboard(); }
};

/* ═══ AUTH FORMS ════════════════════════════════ */
window.handleLogin = async function() {
  const email = document.getElementById('loginEmail')?.value?.trim();
  const pass  = document.getElementById('loginPass')?.value;
  if (!email||!pass) { showToast('ইমেইল ও পাসওয়ার্ড দিন','error'); return; }
  const ok = await A.login(email, pass);
  if (ok) {
    showToast('✅ লগইন সফল!','success');
    updateNav(); showPage('dashboard'); loadDashboard();
  }
};

window.handleRegister = async function() {
  const name  = document.getElementById('regName')?.value?.trim();
  const email = document.getElementById('regEmail')?.value?.trim();
  const pass  = document.getElementById('regPass')?.value;
  if (!name||!email||!pass) { showToast('সব তথ্য দিন','error'); return; }
  if (pass.length<6) { showToast('পাসওয়ার্ড কমপক্ষে ৬ অক্ষর','error'); return; }
  const r = await A.register(name, email, pass);
  if (r) {
    await A.login(email, pass);
    showToast('✅ স্বাগতম '+name+'!','success');
    updateNav(); showPage('dashboard'); loadDashboard();
  }
};

/* ═══ ADMIN ═════════════════════════════════════ */
async function loadAdmin() {
  const [stats, prods, conts, users, pend] = await Promise.all([
    A.stats(), A.productsRaw(), A.allConts(), A.users(), A.pending()
  ]);

  if (stats) {
    setEl('as-prod', stats.total_products);
    setEl('as-cont', stats.open_contracts + stats.matched_contracts);
    setEl('as-user', stats.total_users);
    setEl('as-comm', '৳'+parseFloat(stats.total_commission).toLocaleString());
    setEl('as-pend', stats.pending_deposits + stats.pending_withdrawals);

    // Also update home stats
    setEl('hs-products',  stats.total_products);
    setEl('hs-contracts', stats.open_contracts + stats.matched_contracts);
    setEl('hs-users',     stats.total_users);
  }

  if (prods) { renderAdminPrices(prods); renderAdminProducts(prods); }
  if (conts) renderAdminContracts(conts);
  if (users) renderAdminUsers(users);
  if (pend)  renderAdminPending(pend);
}

function renderAdminPrices(prods) {
  const tb = document.getElementById('adminPriceTable');
  if (!tb) return;
  tb.innerHTML = prods.map(p => {
    const price = parseFloat(p.current_price);
    return `<tr>
      <td>${p.name_bn}</td>
      <td class="mono" style="font-size:0.78rem">${p.unit}</td>
      <td class="mono">৳${price}</td>
      <td><div style="display:flex;gap:6px;align-items:center">
        <input class="price-edit-input" type="number" value="${price}" id="pi-${p.id}" data-old-price="${price}" step="0.5" min="0">
      </div></td>
      <td><button class="btn btn-solid btn-xs" onclick="saveSinglePrice(${p.id})">সেভ</button></td>
    </tr>`;
  }).join('');
}

window.saveSinglePrice = async function(id) {
  const inp = document.getElementById('pi-'+id);
  if (!inp) return;
  const np = parseFloat(inp.value);
  if (!np||np<=0) { showToast('সঠিক দাম দিন','error'); return; }
  const r = await A.updateProd(id, {current_price:np});
  if (r) {
    showToast('✅ দাম আপডেট: ৳'+np,'success');
    if (_prodMap[id]) _prodMap[id].price = np;
  }
};

window.saveAllPricesAPI = async function() {
  const inputs = document.querySelectorAll('.price-edit-input');
  const updates = [];
  inputs.forEach(inp => {
    const id = parseInt(inp.id.replace('pi-',''));
    const p  = parseFloat(inp.value);
    if (id && p>0) updates.push({product_id:id, new_price:p});
  });
  if (!updates.length) { showToast('কোনো পরিবর্তন নেই','error'); return; }
  const r = await A.bulkPrice(updates);
  if (r) { showToast(`✅ ${r.updated}টি পণ্য আপডেট`,'success'); await loadAdmin(); }
};

function renderAdminProducts(prods) {
  const tb = document.getElementById('adminProductTable');
  if (!tb) return;
  tb.innerHTML = prods.map(p => `<tr>
    <td>${p.name_bn}</td><td>${p.category}</td><td>${p.unit}</td>
    <td class="mono text-primary">৳${parseFloat(p.current_price)}</td>
    <td><span class="badge ${p.is_active?'bg-green':'bg-gray'}">${p.is_active?'সক্রিয়':'নিষ্ক্রিয়'}</span></td>
    <td><button class="btn btn-ghost btn-xs" onclick="toggleProd(${p.id},${!p.is_active})">${p.is_active?'বন্ধ':'চালু'}</button></td>
  </tr>`).join('');
}

window.toggleProd = async function(id, active) {
  const r = await A.updateProd(id, {is_active:active});
  if (r) { showToast('✅ আপডেট হয়েছে','success'); loadAdmin(); }
};

function renderAdminContracts(conts) {
  const tb = document.getElementById('adminContractTable');
  if (!tb) return;
  tb.innerHTML = conts.map(c => `<tr>
    <td class="mono text-dim">#${c.contract_code}</td>
    <td>${_prodMap[c.product_id]?.name||'#'+c.product_id}</td>
    <td class="mono">${parseFloat(c.quantity)}</td>
    <td class="mono">৳${parseFloat(c.contract_price)}</td>
    <td class="mono">${c.maturity_date}</td>
    <td><span class="badge ${c.status==='open'?'bg-green':c.status==='matched'?'bg-amber':'bg-gray'}">${c.status}</span></td>
  </tr>`).join('');
}

function renderAdminUsers(users) {
  const tb = document.getElementById('adminUserTable');
  if (!tb) return;
  tb.innerHTML = users.map(u => `<tr>
    <td>${u.name}</td>
    <td style="font-size:0.78rem;color:var(--text-dim)">${u.email}</td>
    <td class="mono text-primary">৳${parseFloat(u.balance).toLocaleString()}</td>
    <td class="mono">${new Date(u.created_at).toLocaleDateString('bn-BD')}</td>
    <td style="display:flex;gap:6px;align-items:center">
      <span class="badge ${u.is_active?'bg-green':'bg-red'}">${u.is_active?'সক্রিয়':'নিষ্ক্রিয়'}</span>
      <button class="btn btn-ghost btn-xs" onclick="adminToggle(${u.id})">${u.is_active?'বন্ধ':'চালু'}</button>
    </td>
  </tr>`).join('');
}

window.adminToggle = async function(id) {
  const r = await A.toggleUser(id);
  if (r) { showToast('✅ আপডেট','success'); loadAdmin(); }
};

function renderAdminPending(txns) {
  const tb = document.getElementById('adminWithdrawalTable');
  if (!tb) return;
  if (!txns.length) { tb.innerHTML='<tr><td colspan="6" class="empty-state">কোনো পেন্ডিং নেই</td></tr>'; return; }
  tb.innerHTML = txns.map(t => `<tr>
    <td>User #${t.user_id}</td>
    <td class="mono text-primary">৳${parseFloat(t.amount).toLocaleString()} <span class="badge bg-gray" style="font-size:0.68rem">${t.txn_type}</span></td>
    <td>${t.payment_method||'—'}</td>
    <td class="mono">${t.account_number||'—'}</td>
    <td class="mono">${new Date(t.created_at).toLocaleDateString('bn-BD')}</td>
    <td style="display:flex;gap:6px">
      <button class="btn btn-green btn-xs" onclick="approveTxn(${t.id},'${t.txn_type}')">✅</button>
      <button class="btn btn-danger btn-xs" onclick="rejectTxn(${t.id})">❌</button>
    </td>
  </tr>`).join('');
}

window.approveTxn = async function(id, type) {
  const r = type==='deposit' ? await A.approveDep(id) : await A.approveWd(id);
  if (r) { showToast('✅ অনুমোদন দেওয়া হয়েছে','success'); loadAdmin(); }
};
window.rejectTxn = async function(id) {
  const r = await A.rejectTxn(id);
  if (r) { showToast('❌ বাতিল করা হয়েছে','error'); loadAdmin(); }
};

/* ════════════════════════════════════════════════════
   PRICE FETCH → PREVIEW → SAVE  (3-step flow)
════════════════════════════════════════════════════ */

let _previewData   = [];   // full preview items from API
let _previewFilter = 'all';

/* ── helpers ── */
function showPriceStep(step) {
  ['priceStep1','priceStep2','priceStep3','priceManual'].forEach(id => {
    const el = document.getElementById(id);
    if (el) el.style.display = 'none';
  });
  const target = step === 1 ? 'priceStep1'
               : step === 2 ? 'priceStep2'
               : step === 3 ? 'priceStep3'
               : 'priceManual';
  const el = document.getElementById(target);
  if (el) el.style.display = '';

  // Step indicator colours
  ['ps1','ps2','ps3'].forEach((id, i) => {
    const s = document.getElementById(id);
    if (!s) return;
    const active = (i + 1) <= (step === 'manual' ? 1 : step);
    s.style.color      = active ? 'var(--primary)'  : 'var(--text-dim)';
    s.style.background = active ? 'var(--primary-glow)' : 'transparent';
    const dot = s.querySelector('span');
    if (dot) {
      dot.style.background = active ? 'var(--primary)'  : 'var(--bg4)';
      dot.style.color      = active ? '#1a1208' : 'var(--text-dim)';
    }
  });
}

window.backToStep1 = function() { showPriceStep(1); };

window.loadAdminManualPrices = async function() {
  showPriceStep('manual');
  const prods = await A.productsRaw();
  if (prods) renderAdminPrices(prods);
};

/* ── STEP 1 → FETCH ── */
window.startFetchPreview = async function() {
  const btn = document.getElementById('fetchBtn');
  if (btn) { btn.disabled = true; btn.innerHTML = '⏳ Fetch হচ্ছে...'; }

  showToast('⏳ Chaldal থেকে দাম আনছে... একটু অপেক্ষা করুন', 'info');

  const data = await A.fetchPreview();

  if (btn) { btn.disabled = false; btn.innerHTML = '🔄 Chaldal থেকে দাম আনুন'; }

  if (!data) {
    showToast('❌ Fetch ব্যর্থ হয়েছে। আবার চেষ্টা করুন।', 'error');
    return;
  }

  _previewData   = data.items || [];
  _previewFilter = 'all';

  // Summary bar
  const sumEl = document.getElementById('fetchSummary');
  if (sumEl) {
    sumEl.innerHTML = [
      { label: `✅ সফল`, count: data.fetched,  cls: 'bg-green' },
      { label: `🔄 পরিবর্তিত`, count: data.changed, cls: 'bg-amber' },
      { label: `❌ ব্যর্থ`,    count: data.failed,  cls: 'bg-red'  },
      { label: `🔗 URL নেই`,   count: data.no_url,  cls: 'bg-gray' },
    ].map(s => `<div class="badge ${s.cls}" style="font-size:0.82rem;padding:6px 14px">
      ${s.label}: <strong>${s.count}</strong>
    </div>`).join('');
  }

  renderPreviewTable('all');
  showPriceStep(2);

  if (data.changed > 0) {
    showToast(`✅ ${data.fetched}টি পণ্য fetch হয়েছে। ${data.changed}টি দাম পরিবর্তিত।`, 'success');
  } else {
    showToast(`ℹ️ ${data.fetched}টি পণ্য fetch হয়েছে। কোনো দাম পরিবর্তিত হয়নি।`, 'info');
  }
};

/* ── STEP 2 → RENDER TABLE ── */
function renderPreviewTable(filter) {
  _previewFilter = filter;
  const tbody = document.getElementById('pricePreviewTable');
  if (!tbody) return;

  let items = _previewData;
  if (filter === 'changed') items = items.filter(i => i.changed);
  if (filter === 'failed')  items = items.filter(i => i.fetch_status === 'failed');
  if (filter === 'no_url')  items = items.filter(i => i.fetch_status === 'no_url');

  const countEl = document.getElementById('previewCount');
  if (countEl) countEl.textContent = `${items.length}টি পণ্য`;

  if (!items.length) {
    tbody.innerHTML = `<tr><td colspan="8" class="empty-state">কোনো পণ্য নেই</td></tr>`;
    return;
  }

  tbody.innerHTML = items.map(item => {
    const fetchedPrice = item.fetched_price;
    const editVal      = fetchedPrice ?? item.old_price;
    const diff         = fetchedPrice ? fetchedPrice - item.old_price : 0;
    const pct          = item.old_price ? Math.round(diff / item.old_price * 100) : 0;
    const diffCls      = diff < 0 ? 'text-green' : diff > 0 ? 'text-red' : 'text-dim';
    const diffTxt      = diff !== 0 ? `${diff>0?'+':''}৳${diff.toFixed(0)} (${pct}%)` : '—';

    const statusBadge =
      item.fetch_status === 'ok'        ? '<span class="badge bg-amber">পরিবর্তিত</span>' :
      item.fetch_status === 'unchanged' ? '<span class="badge bg-gray">অপরিবর্তিত</span>' :
      item.fetch_status === 'failed'    ? `<span class="badge bg-red" title="${item.chaldal_url||''}">ব্যর্থ</span>` :
      '<span class="badge bg-gray">URL নেই</span>';

    // Only pre-check rows that have a fetched price
    const checked = fetchedPrice ? 'checked' : '';

    return `<tr id="prow-${item.product_id}" class="${item.changed?'':'opacity-60'}" style="${!item.changed?'opacity:0.6':''}">
      <td><input type="checkbox" ${checked} data-pid="${item.product_id}" class="prev-chk" style="accent-color:var(--primary)"></td>
      <td>
        <div style="font-weight:600;font-size:0.86rem">${item.name_bn}</div>
        ${item.chaldal_url
          ? `<a href="${item.chaldal_url}" target="_blank" style="font-size:0.7rem;color:var(--text-dim);font-family:var(--font-mono)">Chaldal ↗</a>`
          : `<span style="font-size:0.7rem;color:var(--text-dim)">URL নেই</span>`}
      </td>
      <td class="mono" style="font-size:0.8rem">${item.unit}</td>
      <td class="mono">৳${item.old_price}</td>
      <td class="mono" style="font-weight:700;color:${fetchedPrice?'var(--text)':'var(--text-dim)'}">
        ${fetchedPrice ? '৳'+fetchedPrice : '—'}
      </td>
      <td>
        <div style="display:flex;align-items:center;gap:6px">
          <input
            class="price-edit-input prev-edit"
            type="number"
            value="${editVal}"
            step="0.5" min="0"
            data-pid="${item.product_id}"
            data-old="${item.old_price}"
            id="pi-${item.product_id}"
            oninput="onPreviewInputChange(this)"
            style="width:90px"
          >
          <button class="btn btn-xs btn-ghost" onclick="resetPreviewRow(${item.product_id},${item.old_price})" title="মূল দামে ফিরুন">↺</button>
        </div>
      </td>
      <td class="mono ${diffCls}" style="font-size:0.82rem">${diffTxt}</td>
      <td>${statusBadge}</td>
    </tr>`;
  }).join('');
}

window.filterPreview = function(filter, btn) {
  document.querySelectorAll('#priceStep2 .btn-xs').forEach(b => {
    b.classList.remove('active');
    b.style.background = '';
    b.style.color = '';
  });
  if (btn) {
    btn.classList.add('active');
    btn.style.background = 'var(--primary)';
    btn.style.color = '#1a1208';
  }
  renderPreviewTable(filter);
};

window.toggleAllChecks = function(masterChk) {
  document.querySelectorAll('.prev-chk').forEach(c => c.checked = masterChk.checked);
};

window.onPreviewInputChange = function(inp) {
  const pid     = inp.dataset.pid;
  const oldVal  = parseFloat(inp.dataset.old);
  const newVal  = parseFloat(inp.value) || 0;
  const diff    = newVal - oldVal;
  // Update the diff cell in the same row
  const row = document.getElementById('prow-' + pid);
  if (!row) return;
  const diffCell = row.cells[6];
  if (!diffCell) return;
  const pct  = oldVal ? Math.round(diff/oldVal*100) : 0;
  diffCell.textContent = diff !== 0 ? `${diff>0?'+':''}৳${diff.toFixed(0)} (${pct}%)` : '—';
  diffCell.className   = 'mono ' + (diff < 0 ? 'text-green' : diff > 0 ? 'text-red' : 'text-dim');
  diffCell.style.fontSize = '0.82rem';
};

window.resetPreviewRow = function(pid, oldPrice) {
  const inp = document.getElementById('pi-' + pid);
  if (inp) { inp.value = oldPrice; onPreviewInputChange(inp); }
};

/* ── STEP 3 → SAVE ── */
window.savePreviewedPrices = async function() {
  const checkedInputs = document.querySelectorAll('.prev-chk:checked');
  if (!checkedInputs.length) { showToast('কমপক্ষে একটি পণ্য বেছে নিন', 'error'); return; }

  const updates = [];
  checkedInputs.forEach(chk => {
    const pid   = parseInt(chk.dataset.pid);
    const inp   = document.getElementById('pi-' + pid);
    const price = inp ? parseFloat(inp.value) : 0;
    const oldEl = inp ? parseFloat(inp.dataset.old) : 0;
    if (pid && price > 0) updates.push({ product_id: pid, new_price: price });
  });

  if (!updates.length) { showToast('কোনো পরিবর্তন নেই', 'error'); return; }

  const saveBtn = document.getElementById('saveAllBtn');
  if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = '⏳ সেভ হচ্ছে...'; }

  const r = await A.bulkPrice(updates);

  if (saveBtn) { saveBtn.disabled = false; saveBtn.innerHTML = '💾 পরিবর্তিত দাম সেভ করুন'; }

  if (r) {
    // Update local cache
    updates.forEach(u => { if (_prodMap[u.product_id]) _prodMap[u.product_id].price = u.new_price; });

    // Show step 3
    const sumEl = document.getElementById('savedSummary');
    if (sumEl) sumEl.textContent = `${r.updated}টি পণ্যের দাম সফলভাবে আপডেট হয়েছে।`;
    const timeEl = document.getElementById('savedTime');
    if (timeEl) timeEl.textContent = new Date().toLocaleString('bn-BD');

    showPriceStep(3);
    showToast(`✅ ${r.updated}টি পণ্যের দাম সেভ হয়েছে!`, 'success');

    // Reload admin data in background
    setTimeout(loadAdmin, 1000);
  }
};

window.triggerScrape = async function() {
<<<<<<< HEAD
  showToast('⏳ Background scrape শুরু হয়েছে...', 'info');
  const r = await A.scrape();
  if (r) showToast('✅ ' + r.message, 'success');
=======
  showToast('⏳ Chaldal থেকে দাম আনছে...','info');
  const r = await A.previewScrape();
  if (r) {
    const byId = {};
    (r.updates || []).forEach(u => { byId[u.product_id] = u; });

    let changed = 0, missing = 0;
    document.querySelectorAll('.price-edit-input').forEach(inp => {
      const id = parseInt(inp.id.replace('pi-',''));
      const data = byId[id];
      if (!data || data.new_price == null) {
        missing += 1;
        return;
      }
      const oldPrice = parseFloat(inp.dataset.oldPrice || inp.value || 0);
      inp.value = data.new_price;
      if (data.new_price !== oldPrice) changed += 1;
    });

    showToast(`✅ ফেচ শেষ: ${changed}টি নতুন দাম বসানো হয়েছে, ${missing}টি পাওয়া যায়নি`,'success');
  }
>>>>>>> d2941c8868593e9c0304dcef5be5fb40d08c424c
};
window.triggerSettlement = async function() {
  showToast('⏳ Settlement শুরু হচ্ছে...','info');
  const r = await A.settle();
  if (r) { showToast('✅ '+r.message,'success'); }
};

/* ═══ ADD PRODUCT ════════════════════════════════ */
window.submitAddProduct = async function() {
  const body = {
    name_bn:       document.getElementById('np-bn')?.value?.trim(),
    name_en:       document.getElementById('np-en')?.value?.trim(),
    unit:          document.getElementById('np-unit')?.value?.trim(),
    category:      document.getElementById('np-cat')?.value,
    current_price: parseFloat(document.getElementById('np-price')?.value),
    chaldal_url:   document.getElementById('np-url')?.value?.trim() || null,
  };
  if (!body.name_bn||!body.name_en||!body.unit||!body.current_price) { showToast('সব তথ্য দিন','error'); return; }
  const r = await A.addProduct(body);
  if (r) { showToast('✅ পণ্য যোগ হয়েছে','success'); closeModal('addProductModal'); loadAdmin(); }
};

/* ═══ PAGE ROUTER (override showPage) ═══════════ */
const _baseShowPage = window.showPage;
window.showPage = async function(id) {
  _baseShowPage(id);

  if (id === 'prices') {
    const prods = await loadProds(null, null);
    if (prods) {
      renderGrid(prods);
      buildTicker(prods);
      renderMovers(prods);
      const t = document.getElementById('lastUpdateTime');
      if (t) t.textContent = new Date().toLocaleString('bn-BD');
    }
  }

  if (id === 'contracts') {
    if (!_prods.length) await loadProds();
    const d = await A.contracts('open');
    renderContracts(d);
  }

  if (id === 'history') {
    if (!_prods.length) await loadProds();
    await loadHistory();
  }

  if (id === 'dashboard') {
    if (!Auth.in()) { _baseShowPage('login'); return; }
    await loadDashboard();
  }

  if (id === 'admin') {
    if (!Auth.in() || !Auth.admin()) {
      showToast('অ্যাডমিন অ্যাক্সেস প্রয়োজন','error');
      _baseShowPage('login'); return;
    }
    await loadAdmin();
  }
};

/* ═══ INIT ════════════════════════════════════ */
document.addEventListener('DOMContentLoaded', async () => {
  updateNav();

  // Load products for ticker + movers on home
  const prods = await loadProds();
  if (prods) {
    buildTicker(prods);
    renderMovers(prods);
    setEl('hs-products', prods.length);
  }

  // Restore session
  if (Auth.in()) {
    const me = await A.me();
    if (me) { Auth.setUser(me); updateNav(); }
    else Auth.clear();
  }
});

window.BF = { Auth, A };
