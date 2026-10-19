import { chrome, json, seg, setSeg, el, pct, monthName, num, measureColor } from "./common.js";

chrome("track-record.html");
const d3 = window.d3;
const sc = await json("data/scorecard.json");
const state = { measure: "rent" };
const mEl = document.getElementById("measure");
seg(mEl, ["rent", "price"], state.measure, v => { state.measure = v; render(); }, { rent: "Rent", price: "Sale price" });

const MODEL = "gbm";
const LABEL = Object.fromEntries(sc.table.map(r => [r.method, r.label]));

function tiles() {
  const h = sc.headline[state.measure];
  const box = document.getElementById("tiles");
  box.innerHTML = "";
  const tile = (label, value, sub) => {
    const t = el("div", { class: "tile" });
    t.append(el("div", { class: "label" }, label), el("div", { class: "value" }, value), el("div", { class: "sub" }, sub));
    box.append(t);
  };
  tile("Typical error", pct(h.error12, false), `half of forecasts were closer than this (${num(h.n)} forecasts, ${h.period})`);
  tile("Benchmark error", pct(h.naive12, false), "if you simply assume no change");
  tile("Inside the 8-in-10 range", `${Math.round(h.coverage80 * 100)}%`, "of real outcomes (80% is the target)");
  tile("Direction right", `${Math.round(h.direction * 100)}%`, "of cases where the real move was over 2%");
  document.getElementById("verdict").textContent = h.verdict || "";
}

function chart() {
  const box = document.getElementById("chart");
  box.innerHTML = "";
  const rows = sc.by_h.filter(r => r.measure === state.measure && r.period === "test");
  const methods = [...new Set(rows.map(r => r.method))].sort((a, b) => (b === MODEL) - (a === MODEL));
  const W = Math.max(320, box.clientWidth), H = 300, m = { t: 16, r: W < 560 ? 16 : 190, b: 34, l: 48 };
  const x = d3.scaleLinear().domain([1, 12]).range([m.l, W - m.r]);
  const y = d3.scaleLinear().domain([0, d3.max(rows, r => r.median_error) * 1.12]).nice(4).range([H - m.b, m.t]);
  const svg = d3.select(box).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img")
    .attr("aria-label", "Typical error by months ahead, for each method");
  svg.append("g").attr("class", "grid").selectAll("line").data(y.ticks(4)).join("line")
    .attr("x1", m.l).attr("x2", W - m.r).attr("y1", y).attr("y2", y);
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - m.b})`)
    .call(d3.axisBottom(x).ticks(12).tickFormat(d => d).tickSizeOuter(0));
  svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`)
    .call(d3.axisLeft(y).ticks(4).tickFormat(d => `${Math.round(d * 100)}%`).tickSize(0).tickPadding(8))
    .call(g => g.select(".domain").remove());
  svg.append("text").attr("x", (m.l + W - m.r) / 2).attr("y", H - 2).attr("text-anchor", "middle")
    .attr("fill", "var(--muted)").attr("font-size", 12).text("Months ahead");
  const color = measureColor(state.measure);
  const grays = ["var(--ink-2)", "var(--muted)", "var(--axis)", "var(--ink-2)"];
  const lg = document.getElementById("legend");
  lg.innerHTML = "";
  let gi = 0;
  const ends = [];
  for (const meth of methods) {
    const pts = rows.filter(r => r.method === meth).sort((a, b) => a.h - b.h);
    const isModel = meth === MODEL;
    const c = isModel ? color : grays[gi++ % grays.length];
    svg.append("path").datum(pts).attr("fill", "none").attr("stroke", c).attr("stroke-width", isModel ? 2.5 : 1.5)
      .attr("stroke-dasharray", isModel ? null : gi % 2 ? null : "4 3")
      .attr("d", d3.line().x(d => x(d.h)).y(d => y(d.median_error)));
    const last = pts.at(-1);
    ends.push({ y: y(last.median_error), label: LABEL[meth], v: last.median_error, isModel, c });
    const s = el("span"), k = el("i", { class: "key-line" });
    k.style.background = c; s.append(k, document.createTextNode(LABEL[meth])); lg.append(s);
  }
  if (W >= 560) {   // end labels with simple collision avoidance
    ends.sort((a, b) => a.y - b.y);
    for (let i = 1; i < ends.length; i++) if (ends[i].y - ends[i - 1].y < 15) ends[i].y = ends[i - 1].y + 15;
    for (const e of ends) {
      svg.append("text").attr("x", W - m.r + 10).attr("y", e.y + 4).attr("font-size", 12.5)
        .attr("font-weight", e.isModel ? 650 : 400).attr("fill", e.isModel ? "var(--ink)" : "var(--ink-2)")
        .text(`${pct(e.v, false)} ${e.label.split(" (")[0]}`);
    }
  }
  // table twin
  const t = document.getElementById("h-table");
  t.innerHTML = "";
  const tbl = el("table"), hr = el("tr");
  hr.append(el("th", {}, "Method"));
  for (let h = 1; h <= 12; h++) hr.append(el("th", { class: "num" }, `${h}m`));
  const th = el("thead"); th.append(hr); tbl.append(th);
  const tb = el("tbody");
  for (const meth of methods) {
    const r = el("tr"); r.append(el("td", {}, LABEL[meth]));
    for (let h = 1; h <= 12; h++) {
      const v = rows.find(x => x.method === meth && x.h === h);
      r.append(el("td", { class: "num" }, v ? pct(v.median_error, false) : "·"));
    }
    tb.append(r);
  }
  tbl.append(tb); t.append(tbl);
}

function methods() {
  const t = document.getElementById("methods");
  t.innerHTML = "";
  const rows = sc.table.filter(r => r.measure === state.measure);
  const hr = el("tr");
  for (const [h, n] of [["Method", 0], ["Period", 0], ["3 months", 1], ["6 months", 1], ["12 months", 1], ["8-in-10 range hit", 1], ["Direction right", 1]])
    hr.append(el("th", { class: n ? "num" : "" }, h));
  const th = el("thead"); th.append(hr); t.append(th);
  const tb = el("tbody");
  for (const r of rows) {
    const tr = el("tr");
    const name = el("td"); name.append(r.method === MODEL ? el("b", {}, r.label) : document.createTextNode(r.label));
    tr.append(name, el("td", {}, r.period === "test" ? "Test" : "Development"),
      el("td", { class: "num" }, pct(r.e3, false)), el("td", { class: "num" }, pct(r.e6, false)),
      el("td", { class: "num" }, pct(r.e12, false)), el("td", { class: "num" }, `${Math.round(r.coverage80 * 100)}%`),
      el("td", { class: "num" }, r.direction === null ? "·" : `${Math.round(r.direction * 100)}%`));
    tb.append(tr);
  }
  t.append(tb);
}

function live() {
  const L = sc.live;
  const intro = document.getElementById("live-intro");
  const t = document.getElementById("live");
  t.innerHTML = "";
  const scored = L.archives.filter(a => a.matured > 0);
  intro.textContent = scored.length
    ? `Every forecast published here is saved unchanged. As each month's real data arrives, it is compared with what we said. ${L.archives.length} monthly forecasts published so far, starting ${monthName(L.first_origin)}.`
    : `Every forecast published here is saved unchanged and will be compared with the real data as it arrives. The first forecast was published with data to ${monthName(L.first_origin)}; its first results are scored after next month's data comes in.`;
  const hr = el("tr");
  for (const [h, n] of [["Forecast made with data to", 0], ["Segments", 1], ["Outcomes known so far", 1], ["Typical error so far", 1], ["Inside the 8-in-10 range", 1], ["File", 0]])
    hr.append(el("th", { class: n ? "num" : "" }, h));
  const th = el("thead"); th.append(hr); t.append(th);
  const tb = el("tbody");
  for (const a of [...L.archives].reverse()) {
    const tr = el("tr");
    const f = el("td"); f.append(el("a", { href: a.url }, "CSV"));
    tr.append(el("td", {}, monthName(a.origin)), el("td", { class: "num" }, num(a.segments)),
      el("td", { class: "num" }, num(a.matured)),
      el("td", { class: "num" }, a.matured ? pct(a.median_error, false) : "·"),
      el("td", { class: "num" }, a.matured ? `${Math.round(a.coverage80 * 100)}%` : "·"), f);
    tb.append(tr);
  }
  t.append(tb);
}

function render() { setSeg(mEl, state.measure); tiles(); chart(); methods(); }
const tg = document.getElementById("tbl-toggle");
tg.addEventListener("click", () => {
  const b = document.getElementById("h-table"); b.hidden = !b.hidden;
  tg.setAttribute("aria-expanded", String(!b.hidden)); tg.textContent = b.hidden ? "Show as a table" : "Hide the table";
});
let rt; addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(chart, 150); });
render();
live();
