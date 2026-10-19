import {
  chrome, json, seg, setSeg, el, monthName, addMonths, num, aed, psf, pct, measureColor,
  BEDS_SHORT, homeLabel, sizeNote, relabelBeds,
} from "./common.js";
import { fanChart } from "./chart.js";

chrome("index.html");

const state = { slug: null, ptype: "apartment", beds: "1", measure: "rent", span: "5y" };
const q = new URLSearchParams(location.search);
for (const k of ["slug", "ptype", "beds", "measure", "span"]) if (q.get(k)) state[k] = q.get(k);

const [areas, meta, score] = await Promise.all([json("data/areas.json"), json("data/meta.json"), json("data/scorecard.json")]);
const bySlug = new Map(areas.map(a => [a.slug, a]));
if (!bySlug.has(state.slug)) state.slug = meta.default_area && bySlug.has(meta.default_area) ? meta.default_area : areas[0].slug;

// hero facts
const facts = document.getElementById("facts");
const fact = (b, t) => { const s = el("span"); s.append(el("b", {}, b), document.createTextNode(" " + t)); facts.append(s); };
fact(num(areas.length - 1), "areas");
fact(`${(meta.deals.rent / 1e6).toFixed(1)}M`, "lease contracts");
fact(`${(meta.deals.price / 1e6).toFixed(1)}M`, "sales");
fact(monthName(meta.data_through), "latest data");

// area combobox
const combo = document.getElementById("combo"), input = document.getElementById("area-input"), list = document.getElementById("area-list");
let options = [], active = -1;
const norm = s => s.toLowerCase().normalize("NFD").replace(/[^a-z0-9 ]/g, "");
function renderList(filter) {
  const f = norm(filter || "");
  options = areas.filter(a => !f || [a.name, a.official, ...a.aka].some(n => norm(n).includes(f)));
  list.innerHTML = "";
  options.forEach((a, i) => {
    const li = el("li", { role: "option", id: `opt-${i}`, "aria-selected": String(i === active) });
    li.append(el("span", {}, a.name));
    if (a.official && a.official !== a.name) li.append(el("span", { class: "o" }, a.official));
    li.addEventListener("mousedown", e => { e.preventDefault(); pick(a.slug); });
    list.append(li);
  });
  if (!options.length) list.append(el("li", { class: "muted" }, "No area with enough deals matches"));
}
function open(v) { combo.classList.toggle("open", v); input.setAttribute("aria-expanded", String(v)); }
input.addEventListener("focus", () => { input.select(); active = -1; renderList(""); open(true); });
input.addEventListener("input", () => { active = 0; renderList(input.value); open(true); });
input.addEventListener("blur", () => { open(false); input.value = bySlug.get(state.slug).name; });
input.addEventListener("keydown", e => {
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    active = Math.max(0, Math.min(options.length - 1, active + (e.key === "ArrowDown" ? 1 : -1)));
    renderList(input.value);
    document.getElementById(`opt-${active}`)?.scrollIntoView({ block: "nearest" });
  } else if (e.key === "Enter" && options[Math.max(active, 0)]) {
    pick(options[Math.max(active, 0)].slug); input.blur();
  } else if (e.key === "Escape") input.blur();
});
function pick(slug) { state.slug = slug; open(false); input.value = bySlug.get(slug).name; update(); }

const ptypeEl = document.getElementById("ptype"), bedsEl = document.getElementById("beds"),
  measureEl = document.getElementById("measure"), spanEl = document.getElementById("span");
seg(ptypeEl, ["apartment", "villa"], state.ptype, v => { state.ptype = v; update(); }, { apartment: "Apartment", villa: "Villa / townhouse" });
seg(bedsEl, ["studio", "1", "2", "3", "4+", "all"], state.beds, v => { state.beds = v; update(); }, BEDS_SHORT);
seg(measureEl, ["rent", "price"], state.measure, v => { state.measure = v; update(); }, { rent: "Rent", price: "Sale price" });
seg(spanEl, ["3y", "5y", "all"], state.span, v => { state.span = v; draw(); }, { "3y": "3 years", "5y": "5 years", all: "Since 2013" });

let current = null;
async function update() {
  const a = bySlug.get(state.slug);
  input.value = a.name;
  const av = a.available;
  // keep the choice if possible, else fall back to what exists for this area
  const ptypes = ["apartment", "villa"].filter(p => av.rent?.[p] || av.price?.[p]);
  if (!ptypes.includes(state.ptype)) state.ptype = ptypes[0];
  const bedsFor = m => av[m]?.[state.ptype] || [];
  const measures = ["rent", "price"].filter(m => bedsFor(m).length);
  if (!measures.includes(state.measure)) state.measure = measures[0];
  const beds = bedsFor(state.measure);
  if (!beds.includes(state.beds)) state.beds = beds.includes("all") ? "all" : beds[0];
  setSeg(ptypeEl, state.ptype, ptypes);
  relabelBeds(bedsEl, state.ptype);
  setSeg(bedsEl, state.beds, beds);
  document.getElementById("beds-note").textContent = sizeNote(meta.size_groups, state.ptype, state.beds);
  setSeg(measureEl, state.measure, measures.filter(m => bedsFor(m).includes(state.beds)).length ? ["rent", "price"].filter(m => bedsFor(m).includes(state.beds)) : measures);
  const url = new URL(location.href);
  for (const k of ["slug", "ptype", "beds", "measure"]) url.searchParams.set(k, state[k]);
  history.replaceState(null, "", url);
  document.getElementById("panel").classList.add("loading");
  const data = await json(`data/areas/${a.slug}.json`);
  document.getElementById("panel").classList.remove("loading");
  current = { a, data, s: data.series[`${state.measure}|${state.ptype}|${state.beds}`] };
  answer();
  draw();
}

function answer() {
  const { a, s } = current;
  const box = document.getElementById("answer");
  box.innerHTML = "";
  const rent = state.measure === "rent";
  const size = s.now.typical_size;
  const where = a.slug === "all-dubai" ? "across Dubai" : `in ${a.name}`;
  const lastM = s.history[s.history.length - 1][0];
  const fm = s.forecast.months[s.forecast.months.length - 1];
  const c = s.change12;
  const fLevel = s.forecast.q50[s.forecast.q50.length - 1];

  const c1 = el("div");
  const qn = el("div", { class: "question" });
  qn.append(el("span", { class: "what" }, rent ? "Typical yearly rent of a " : "Typical sale price of a "),
    document.createTextNode(`${homeLabel(state.ptype, state.beds).replace(/s of all sizes$/, " of any size")} ${where}`));
  c1.append(qn);
  const t1 = el("div", { class: "stat", style: "margin-top:16px" });
  t1.append(el("div", { class: "label" }, `Today (${monthName(addMonths(lastM, -2))} to ${monthName(lastM)})`));
  const v1 = el("div", { class: "value" }, aed(s.now.level * size));
  t1.append(v1);
  t1.append(el("div", { class: "sub" }, `${psf(s.now.level)} per sq ft${rent ? " a year" : ""} · typical size ${num(size)} sq ft · ${num(s.now.deals3)} ${rent ? "new leases" : "sales"} in 3 months`));
  c1.append(t1);

  const c2 = el("div", { class: "stat" });
  c2.append(el("div", { class: "label" }, `In 12 months (${monthName(fm)})`));
  const v2 = el("div", { class: "value" }, aed(fLevel * size));
  c2.append(v2);
  const d = el("span", { class: `delta ${c.q50 > 0.005 ? "up" : c.q50 < -0.005 ? "down" : ""}` },
    `${c.q50 > 0.005 ? "▲" : c.q50 < -0.005 ? "▼" : "■"} ${pct(c.q50)}`);
  const dl = el("div", { style: "display:flex;align-items:center;gap:10px;margin-top:6px" });
  dl.append(d, el("span", { class: "small ink2" }, "most likely change"));
  c2.append(dl);
  // 80% range bar
  const lo = s.forecast.q10.at(-1), hi = s.forecast.q90.at(-1), q25 = s.forecast.q25.at(-1), q75 = s.forecast.q75.at(-1);
  const pad = (hi - lo) * 0.25, a0 = lo - pad, a1 = hi + pad, P = v => `${((v - a0) / (a1 - a0)) * 100}%`;
  const bar = el("div", { class: "range-bar", "aria-hidden": "true" });
  const i80 = el("i"); i80.style.left = P(lo); i80.style.width = `calc(${P(hi)} - ${P(lo)})`; i80.style.background = measureColor(state.measure); i80.style.opacity = 0.25;
  const i50 = el("i"); i50.style.left = P(q25); i50.style.width = `calc(${P(q75)} - ${P(q25)})`; i50.style.background = measureColor(state.measure); i50.style.opacity = 0.55;
  const tick = el("b"); tick.style.left = `calc(${P(fLevel)} - 1.5px)`;
  bar.append(i80, i50, tick);
  c2.append(bar);
  c2.append(el("div", { class: "sub" }, `8 in 10 chance between ${aed(lo * size)} and ${aed(hi * size)}`));

  const c3 = el("div", { class: "stat" });
  c3.append(el("div", { class: "label" }, "How reliable is this?"));
  const h = score.headline?.[state.measure];
  if (h) {
    c3.append(el("p", { class: "small", style: "margin-top:8px" },
      `In our ${h.period} test, 12-month ${rent ? "rent" : "price"} forecasts were off by ${pct(h.error12, false, 1)} in a typical case, against ${pct(h.naive12, false, 1)} for simply assuming no change. ${Math.round(h.coverage80 * 100)}% of real outcomes fell inside the 8-in-10 range.`));
  }
  const y = s.now.gross_yield;
  if (y) c3.append(el("p", { class: "small" }, `Gross rental yield ${where}: ${pct(y, false, 1)} a year (typical rent ÷ typical price, before costs).`));
  const link = el("a", { class: "small", href: "track-record.html" }, "Track record →");
  c3.append(link);
  box.append(c1, c2, c3);
}

function draw() {
  if (!current) return;
  const { a, s } = current;
  setSeg(spanEl, state.span);
  const rent = state.measure === "rent";
  const lastM = s.history.at(-1)[0];
  const from = state.span === "all" ? null : addMonths(lastM, state.span === "3y" ? -36 : -60);
  const color = measureColor(state.measure);
  document.getElementById("chart-title").textContent =
    `${rent ? "Yearly rent" : "Sale price"} per sq ft: ${homeLabel(state.ptype, state.beds)}, ${a.slug === "all-dubai" ? "all of Dubai" : a.name}`;
  const lg = document.getElementById("legend");
  lg.innerHTML = "";
  const key = (cls, op, t, dash) => {
    const s = el("span"); const k = el("i", { class: cls });
    k.style.background = dash ? `repeating-linear-gradient(90deg, ${color} 0 5px, transparent 5px 9px)` : color;
    if (op) k.style.opacity = op;
    s.append(k, document.createTextNode(t)); lg.append(s);
  };
  key("key-line", 0, "Actual (3-month level)");
  key("key-line", 0, "Forecast, most likely", true);
  key("key-band", 0.45, "50% range");
  key("key-band", 0.2, "80% range");
  const chart = document.getElementById("chart");
  fanChart(chart, {
    history: s.history, forecast: s.forecast, color, from,
    unitLabel: rent ? "AED per sq ft, per year" : "AED per sq ft",
    unitShort: rent ? "AED per sq ft a year" : "AED per sq ft",
    size: s.now.typical_size, homeLabel: rent ? "Typical home, a year" : "Typical home",
    aria: `${rent ? "Rent" : "Price"} per square foot over time with a 12-month forecast`,
  });
  document.getElementById("chart-note").textContent =
    `Each point is the typical deal of the 3 months ending that month. Months with fewer than 12 deals are left out. Data to ${monthName(lastM)}.`;
  table();
}

function table() {
  const { s } = current;
  const box = document.getElementById("tbl");
  box.innerHTML = "";
  const t = el("table"), th = el("thead"), tr = el("tr");
  for (const [h, n] of [["Month", 0], ["Per sq ft", 1], ["50% range", 1], ["80% range", 1], ["Deals", 1]]) tr.append(el("th", { class: n ? "num" : "" }, h));
  th.append(tr); t.append(th);
  const tb = el("tbody");
  for (const [ym, v, n] of s.history.slice(-24)) {
    const r = el("tr");
    r.append(el("td", {}, monthName(ym)), el("td", { class: "num" }, num(v)), el("td", { class: "num" }, "·"), el("td", { class: "num" }, "·"), el("td", { class: "num" }, num(n)));
    tb.append(r);
  }
  s.forecast.months.forEach((ym, i) => {
    const r = el("tr");
    r.append(el("td", {}, `${monthName(ym)} (forecast)`), el("td", { class: "num" }, num(s.forecast.q50[i])),
      el("td", { class: "num" }, `${num(s.forecast.q25[i])} to ${num(s.forecast.q75[i])}`),
      el("td", { class: "num" }, `${num(s.forecast.q10[i])} to ${num(s.forecast.q90[i])}`), el("td", { class: "num" }, "·"));
    tb.append(r);
  });
  t.append(tb); box.append(t);
}
const tg = document.getElementById("tbl-toggle");
tg.addEventListener("click", () => {
  const box = document.getElementById("tbl"); box.hidden = !box.hidden;
  tg.setAttribute("aria-expanded", String(!box.hidden)); tg.textContent = box.hidden ? "Show as a table" : "Hide the table";
});
let rt; addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(draw, 150); });
update();
