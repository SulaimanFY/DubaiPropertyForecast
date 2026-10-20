// History + forecast fan chart (one series, one y-axis), with a crosshair tooltip.
import { toDate, monthName, num, aed, el } from "./common.js";

const d3 = window.d3;

export function fanChart(container, opt) {
  // opt: history [[ym, level, deals]], forecast {months, q10..q90}, color, unitLabel, size (typical sq ft),
  //      from (ym or null), amountLabel ("a year" | "")
  container.innerHTML = "";
  const W = Math.max(320, container.clientWidth);
  const H = W < 560 ? 280 : 340;
  const m = { t: 18, r: W < 560 ? 14 : 64, b: 30, l: W < 560 ? 46 : 58 };
  const hist = opt.history.filter(d => !opt.from || d[0] >= opt.from).map(d => ({ date: toDate(d[0]), ym: d[0], v: d[1], n: d[2] }));
  const f = opt.forecast;
  const last = hist[hist.length - 1];
  const fc = f.months.map((ym, i) => ({ date: toDate(ym), ym, q10: f.q10[i], q25: f.q25[i], q50: f.q50[i], q75: f.q75[i], q90: f.q90[i] }));
  const band = [{ date: last.date, ym: last.ym, q10: last.v, q25: last.v, q50: last.v, q75: last.v, q90: last.v }, ...fc];

  const x = d3.scaleTime().domain([hist[0].date, fc[fc.length - 1].date]).range([m.l, W - m.r]);
  const lo = d3.min([...hist.map(d => d.v), ...fc.map(d => d.q10)]);
  const hi = d3.max([...hist.map(d => d.v), ...fc.map(d => d.q90)]);
  const y = d3.scaleLinear().domain([lo * 0.92, hi * 1.05]).nice(5).range([H - m.b, m.t]);

  const svg = d3.select(container).append("svg").attr("viewBox", `0 0 ${W} ${H}`).attr("role", "img")
    .attr("aria-label", opt.aria || "Chart");
  svg.append("g").attr("class", "grid").selectAll("line").data(y.ticks(5)).join("line")
    .attr("x1", m.l).attr("x2", W - m.r).attr("y1", y).attr("y2", y);
  const years = d3.timeYear.every(x.domain()[1] - x.domain()[0] > 8 * 365 * 864e5 ? 2 : 1);
  svg.append("g").attr("class", "axis").attr("transform", `translate(0,${H - m.b})`)
    .call(d3.axisBottom(x).ticks(years).tickFormat(d3.timeFormat("%Y")).tickSizeOuter(0));
  svg.append("g").attr("class", "axis").attr("transform", `translate(${m.l},0)`)
    .call(d3.axisLeft(y).ticks(5).tickFormat(v => num(v)).tickSize(0).tickPadding(8))
    .call(g => g.select(".domain").remove());
  svg.append("text").attr("x", m.l).attr("y", 10).attr("fill", "var(--muted)").attr("font-size", 12)
    .text(opt.unitLabel);

  const area = (a, b) => d3.area().x(d => x(d.date)).y0(d => y(d[a])).y1(d => y(d[b])).curve(d3.curveMonotoneX);
  svg.append("path").datum(band).attr("d", area("q10", "q90")).attr("fill", opt.color).attr("fill-opacity", 0.12);
  svg.append("path").datum(band).attr("d", area("q25", "q75")).attr("fill", opt.color).attr("fill-opacity", 0.22);

  const todayX = x(last.date);
  svg.append("line").attr("x1", todayX).attr("x2", todayX).attr("y1", m.t).attr("y2", H - m.b)
    .attr("stroke", "var(--axis)");
  svg.append("text").attr("x", todayX + 6).attr("y", m.t + 10).attr("fill", "var(--muted)").attr("font-size", 12)
    .text("Today");

  const line = d3.line().x(d => x(d.date)).y(d => y(d.v)).curve(d3.curveMonotoneX);
  svg.append("path").datum(hist).attr("d", line).attr("fill", "none").attr("stroke", opt.color)
    .attr("stroke-width", 2).attr("stroke-linejoin", "round").attr("stroke-linecap", "round");
  svg.append("path").datum(band).attr("d", d3.line().x(d => x(d.date)).y(d => y(d.q50)).curve(d3.curveMonotoneX))
    .attr("fill", "none").attr("stroke", opt.color).attr("stroke-width", 2).attr("stroke-dasharray", "5 4")
    .attr("stroke-linecap", "round");
  const end = fc[fc.length - 1];
  svg.append("circle").attr("cx", x(last.date)).attr("cy", y(last.v)).attr("r", 4.5).attr("fill", opt.color)
    .attr("stroke", "var(--surface)").attr("stroke-width", 2);
  svg.append("circle").attr("cx", x(end.date)).attr("cy", y(end.q50)).attr("r", 4.5).attr("fill", opt.color)
    .attr("stroke", "var(--surface)").attr("stroke-width", 2);
  if (W >= 560) {
    svg.append("text").attr("x", x(end.date) + 8).attr("y", y(end.q50) + 4).attr("fill", "var(--ink)")
      .attr("font-size", 13).attr("font-weight", 650).text(num(end.q50));
  }

  // hover layer
  const tip = el("div", { class: "tip", role: "status" });
  container.append(tip);
  const cross = svg.append("line").attr("y1", m.t).attr("y2", H - m.b).attr("stroke", "var(--ink-2)")
    .attr("stroke-width", 1).attr("opacity", 0);
  const dot = svg.append("circle").attr("r", 4.5).attr("fill", opt.color).attr("stroke", "var(--surface)")
    .attr("stroke-width", 2).attr("opacity", 0);
  const all = [...hist.map(d => ({ ...d, kind: "h" })), ...fc.map(d => ({ ...d, kind: "f" }))];
  const bis = d3.bisector(d => d.date).center;
  const show = d => {
    const px = x(d.date), v = d.kind === "h" ? d.v : d.q50;
    cross.attr("x1", px).attr("x2", px).attr("opacity", 1);
    dot.attr("cx", px).attr("cy", y(v)).attr("opacity", 1);
    tip.innerHTML = "";
    tip.append(el("div", { class: "t" }, monthName(d.ym, true) + (d.kind === "f" ? " (forecast)" : "")));
    const row = (label, value, key) => {
      const r = el("div", { class: "r" });
      const s = el("span");
      if (key) { const k = el("i", { class: key === "line" ? "key-line" : "key-band" }); k.style.background = opt.color; if (key === "band") k.style.opacity = 0.35; s.append(k); }
      s.append(document.createTextNode(label));
      r.append(s, el("b", {}, value));
      tip.append(r);
    };
    if (d.kind === "h") {
      row(opt.unitShort, num(d.v), "line");
      if (opt.size) row(opt.homeLabel, aed(d.v * opt.size));
      row("Deals that month", num(d.n));
    } else {
      row("Most likely", num(d.q50), "line");
      row("50% range", `${num(d.q25)} to ${num(d.q75)}`, "band");
      row("80% range", `${num(d.q10)} to ${num(d.q90)}`, "band");
      if (opt.size) row(opt.homeLabel, aed(d.q50 * opt.size));
    }
    const tw = tip.offsetWidth, cw = container.clientWidth;
    // right of the crosshair, or left of it when there is no room (never over the hovered point)
    tip.style.left = `${Math.max(0, px + 14 + tw <= cw ? px + 14 : px - 14 - tw)}px`;
    tip.style.top = `${Math.max(0, y(v) - 70)}px`;
    tip.style.opacity = 1;
  };
  svg.append("rect").attr("x", m.l).attr("y", m.t).attr("width", W - m.l - m.r).attr("height", H - m.t - m.b)
    .attr("fill", "transparent").attr("tabindex", 0)
    .on("pointermove", ev => show(all[bis(all, x.invert(d3.pointer(ev)[0]))]))
    .on("pointerleave blur", () => { tip.style.opacity = 0; cross.attr("opacity", 0); dot.attr("opacity", 0); })
    .on("focus", () => show(all[hist.length - 1]))
    .on("keydown", ev => {
      const cur = all.findIndex(d => +d.date === +x.invert(+cross.attr("x1")));
      const i = Math.max(0, Math.min(all.length - 1, (cur < 0 ? hist.length - 1 : cur) + (ev.key === "ArrowRight" ? 1 : ev.key === "ArrowLeft" ? -1 : 0)));
      show(all[i]);
    });
}
