import { chrome, json, seg, setSeg, el, num, pct, psf, measureColor, BEDS_SHORT } from "./common.js";

chrome("rankings.html");
const rows = await json("data/rankings.json");
const state = { measure: "rent", ptype: "apartment", beds: "all", sort: "q50", dir: -1, search: "" };
const q = new URLSearchParams(location.search);
for (const k of ["measure", "ptype", "beds"]) if (q.get(k)) state[k] = q.get(k);

const mEl = document.getElementById("measure"), pEl = document.getElementById("ptype"), bEl = document.getElementById("beds");
seg(mEl, ["rent", "price"], state.measure, v => { state.measure = v; render(); }, { rent: "Rent", price: "Sale price" });
seg(pEl, ["apartment", "villa"], state.ptype, v => { state.ptype = v; render(); }, { apartment: "Apartment", villa: "Villa / townhouse" });
seg(bEl, ["all", "studio", "1", "2", "3", "4+"], state.beds, v => { state.beds = v; render(); }, BEDS_SHORT);
document.getElementById("search").addEventListener("input", e => { state.search = e.target.value.toLowerCase(); table(); });

const NS = "http://www.w3.org/2000/svg";
function bars(box, list, dom) {
  box.innerHTML = "";
  const color = measureColor(state.measure);
  const W = 300, H = 22, X = v => ((v - dom[0]) / (dom[1] - dom[0])) * W;
  for (const r of list) {
    const row = el("div", { class: "rank-row" });
    const nm = el("div", { class: "nm" });
    const a = el("a", { href: `index.html?slug=${r.slug}&ptype=${r.ptype}&beds=${r.beds}&measure=${r.measure}` }, r.name);
    nm.append(a);
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("viewBox", `0 0 ${W} ${H}`); svg.setAttribute("preserveAspectRatio", "none");
    svg.setAttribute("aria-hidden", "true"); svg.style.width = "100%"; svg.style.height = `${H}px`;
    const mk = (tag, at) => { const e = document.createElementNS(NS, tag); for (const [k, v] of Object.entries(at)) e.setAttribute(k, v); svg.append(e); return e; };
    mk("line", { x1: X(0), x2: X(0), y1: 0, y2: H, stroke: "var(--axis)", "stroke-width": 1, "vector-effect": "non-scaling-stroke" });
    mk("line", { x1: X(r.q10), x2: X(r.q90), y1: H / 2, y2: H / 2, stroke: color, "stroke-opacity": 0.45, "stroke-width": 2, "vector-effect": "non-scaling-stroke" });
    const x0 = Math.min(X(0), X(r.q50)), w = Math.max(1.5, Math.abs(X(r.q50) - X(0)));
    mk("rect", { x: x0, y: 5, width: w, height: 12, rx: 3, fill: color });
    const v = el("div", { class: "v" }, pct(r.q50));
    row.title = `${r.name}: most likely ${pct(r.q50)}, 8 in 10 chance between ${pct(r.q10)} and ${pct(r.q90)}`;
    row.append(nm, svg, v);
    box.append(row);
  }
}

let cur = [];
function render() {
  setSeg(mEl, state.measure); setSeg(pEl, state.ptype); setSeg(bEl, state.beds);
  cur = rows.filter(r => r.measure === state.measure && r.ptype === state.ptype && r.beds === state.beds);
  const sorted = [...cur].sort((a, b) => b.q50 - a.q50);
  const n = Math.min(12, Math.floor(sorted.length / 2));
  const up = sorted.slice(0, n), down = sorted.slice(-n).reverse();
  const shown = [...up, ...down];
  const dom = shown.length ? [Math.min(0, ...shown.map(r => r.q10)), Math.max(0, ...shown.map(r => r.q90))] : [-0.1, 0.1];
  const what = state.measure === "rent" ? "rent" : "price";
  document.getElementById("up-sub").textContent = `Most likely ${what} change over 12 months, ${cur.length} areas ranked`;
  document.getElementById("down-sub").textContent = `Smallest expected ${what} change (or biggest fall)`;
  bars(document.getElementById("up"), up, dom);
  bars(document.getElementById("down"), down, dom);
  const url = new URL(location.href);
  for (const k of ["measure", "ptype", "beds"]) url.searchParams.set(k, state[k]);
  history.replaceState(null, "", url);
  table();
}

const COLS = [
  ["name", "Area", false], ["now", "Today, per sq ft", true], ["q50", "Most likely change", true],
  ["q10", "8-in-10 range", true], ["deals3", "Deals, 3 months", true],
];
function table() {
  const t = document.getElementById("table");
  t.innerHTML = "";
  const th = el("thead"), tr = el("tr");
  for (const [k, label, n] of COLS) {
    const c = el("th", { class: n ? "num" : "", "data-sort": k }, label);
    if (state.sort === k) c.setAttribute("aria-sort", state.dir < 0 ? "descending" : "ascending");
    c.addEventListener("click", () => { state.dir = state.sort === k ? -state.dir : (k === "name" ? 1 : -1); state.sort = k; table(); });
    tr.append(c);
  }
  th.append(tr); t.append(th);
  const tb = el("tbody");
  const list = cur.filter(r => !state.search || r.name.toLowerCase().includes(state.search))
    .sort((a, b) => (typeof a[state.sort] === "string" ? a[state.sort].localeCompare(b[state.sort]) : a[state.sort] - b[state.sort]) * state.dir);
  for (const r of list) {
    const row = el("tr");
    const td = el("td");
    td.append(el("a", { href: `index.html?slug=${r.slug}&ptype=${r.ptype}&beds=${r.beds}&measure=${r.measure}` }, r.name));
    row.append(td, el("td", { class: "num" }, `${psf(r.now)}${state.measure === "rent" ? " /yr" : ""}`),
      el("td", { class: "num" }, pct(r.q50)), el("td", { class: "num" }, `${pct(r.q10)} to ${pct(r.q90)}`),
      el("td", { class: "num" }, num(r.deals3)));
    tb.append(row);
  }
  t.append(tb);
}
render();
