// Shared page chrome, formatting and data loading.
export const REPO = "https://github.com/SulaimanFY/DubaiPropertyForecast";

const NAV = [
  ["index.html", "Forecast"],
  ["rankings.html", "Rankings"],
  ["track-record.html", "Track record"],
  ["how-it-works.html", "How it works"],
];

const LOGO = `<svg width="28" height="28" viewBox="0 0 28 28" aria-hidden="true">
  <rect width="28" height="28" rx="7" fill="#c8a96a"/>
  <path d="M6 21V13h3v8M11 21V9h3v12M16 21v-6h3v6" fill="none" stroke="#10284a" stroke-width="2" stroke-linejoin="round"/>
  <path d="M5.5 10.5 11.5 6l5 3.5L22.5 5" fill="none" stroke="#10284a" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
  <circle cx="22.5" cy="5" r="1.8" fill="#10284a"/></svg>`;

export function chrome(active) {
  const top = document.createElement("header");
  top.className = "top";
  top.innerHTML = `<div class="wrap"><a class="brand" href="index.html">${LOGO}<span>Dubai Property Forecast</span></a>
    <nav class="nav" aria-label="Main">${NAV.map(([h, t]) =>
      `<a href="${h}"${h === active ? ' aria-current="page"' : ""}>${t}</a>`).join("")}</nav></div>`;
  document.body.prepend(top);
  const foot = document.createElement("footer");
  foot.innerHTML = `<div class="wrap"><div>
      <p><b class="ink2">Data:</b> Dubai Land Department open data (sales transactions and Ejari rent contracts),
      Government of Dubai. This is an independent project. It is not affiliated with or endorsed by the
      Dubai Land Department or the Government of Dubai.</p>
      <p>Forecasts are statistical estimates with ranges, not financial or investment advice.</p></div>
      <div><p>Built by <a href="https://kalson.ae">Sulaiman Fayyaz, Kalson</a>.<br>
      <a href="${REPO}">Code and data on GitHub</a></p><p id="foot-updated"></p></div></div>`;
  document.body.append(foot);
  json("data/meta.json").then(m => {
    document.getElementById("foot-updated").textContent =
      `Updated ${longDate(m.updated)} with data to ${monthName(m.data_through)}. Next update around ${longDate(m.next_update)}.`;
  }).catch(() => {});
}

const cache = new Map();
export function json(path) {
  if (!cache.has(path)) cache.set(path, fetch(path).then(r => { if (!r.ok) throw new Error(path); return r.json(); }));
  return cache.get(path);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
export const monthName = (ym, long = false) => {
  const [y, m] = ym.split("-").map(Number);
  return `${(long ? MONTHS_LONG : MONTHS)[m - 1]} ${y}`;
};
export const longDate = iso => {
  const [y, m, d] = iso.split("-").map(Number);
  return `${d} ${MONTHS_LONG[m - 1]} ${y}`;
};
export const toDate = ym => { const [y, m] = ym.split("-").map(Number); return new Date(y, m - 1, 1); };
export const addMonths = (ym, k) => {
  const [y, m] = ym.split("-").map(Number);
  const t = y * 12 + (m - 1) + k;
  return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, "0")}`;
};

const nf0 = new Intl.NumberFormat("en-US", { maximumFractionDigits: 0 });
export const num = v => nf0.format(v);
export const roundNice = v => {
  const a = Math.abs(v);
  const step = a >= 1e6 ? 10000 : a >= 1e5 ? 1000 : a >= 1e4 ? 500 : 50;
  return Math.round(v / step) * step;
};
export const aed = v => `AED ${num(roundNice(v))}`;
export const aedShort = v => {
  const a = Math.abs(v);
  if (a >= 1e6) return `AED ${(v / 1e6).toFixed(a >= 1e7 ? 1 : 2)}M`;
  if (a >= 1e3) return `AED ${Math.round(v / 1e3)}K`;
  return `AED ${num(v)}`;
};
export const psf = v => `AED ${num(v)}`;
export const pct = (v, sign = true, nd = 1) => `${sign && v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v * 100).toFixed(nd)}%`;

export const BEDS_LABEL = { studio: "Studio", "1": "1 bedroom", "2": "2 bedrooms", "3": "3 bedrooms", "4+": "4+ bedrooms", all: "All sizes" };
export const BEDS_SHORT = { studio: "Studio", "1": "1", "2": "2", "3": "3", "4+": "4+", all: "All" };
export const homeLabel = (ptype, beds) => {
  const t = ptype === "villa" ? "villa or townhouse" : "apartment";
  if (beds === "all") return `${t}s of all sizes`;
  if (beds === "studio") return ptype === "villa" ? "studio villa" : "studio apartment";
  return `${beds === "4+" ? "4+ bedroom" : beds + "-bedroom"} ${t}`;
};
export const measureColor = m => getComputedStyle(document.documentElement).getPropertyValue(m === "rent" ? "--rent" : "--price").trim();

export function seg(el, values, current, onPick, labels = {}) {
  el.innerHTML = "";
  for (const v of values) {
    const b = document.createElement("button");
    b.type = "button";
    b.dataset.v = v;
    b.textContent = labels[v] ?? v;
    b.setAttribute("aria-pressed", String(v === current));
    b.addEventListener("click", () => onPick(v));
    el.append(b);
  }
}
export function setSeg(el, current, enabled) {
  for (const b of el.querySelectorAll("button")) {
    b.setAttribute("aria-pressed", String(b.dataset.v === current));
    if (enabled) b.disabled = !enabled.includes(b.dataset.v);
  }
}

export function el(tag, attrs = {}, text) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v; else e.setAttribute(k, v);
  }
  if (text !== undefined) e.textContent = text;
  return e;
}
