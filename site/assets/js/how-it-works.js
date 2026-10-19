import { chrome, json, el, longDate, monthName, REPO } from "./common.js";

chrome("how-it-works.html");
document.getElementById("repo-link").href = REPO;
const [meta, checks] = await Promise.all([json("data/meta.json"), json("data/checks.json")]);
document.getElementById("attribution").textContent = meta.attribution;
const links = document.getElementById("source-links");
for (const [t, h] of Object.entries(meta.source_links || {})) {
  const li = document.createElement("li"), a = document.createElement("a");
  a.href = h; a.textContent = t; li.append(a); links.append(li);
}
const rl = document.getElementById("run-line");
rl.append(document.createTextNode(`Last run ${longDate(meta.updated)}, with data to ${monthName(meta.data_through)}. `));
if (meta.run_url) rl.append(el("a", { href: meta.run_url }, "See the run log on GitHub"));

const list = checks.checks || [];
const failed = list.filter(c => c.status === "fail").length;
document.getElementById("checks-sub").textContent =
  `${list.length} checks on the ${checks.run} update: ${list.length - failed} passed${failed ? `, ${failed} failed` : ""}.`;
const t = document.getElementById("checks");
const hr = el("tr");
for (const [h, n] of [["Check", 0], ["Data", 0], ["Value", 1], ["Rule", 0], ["Result", 0]]) hr.append(el("th", { class: n ? "num" : "" }, h));
const th = el("thead"); th.append(hr); t.append(th);
const tb = el("tbody");
const fmt = c => c.value === null ? "·"
  : c.unit === "share" ? `${(c.value * 100).toFixed(c.value < 0.01 ? 2 : 1)}%`
  : c.unit === "ratio" ? `${c.value.toFixed(2)}×`
  : c.value.toLocaleString("en-US", { maximumFractionDigits: 0 });
const WHAT = { rent: "Leases", price: "Sales", model: "Model" };
for (const c of list) {
  const r = el("tr");
  r.append(el("td", {}, c.check[0].toUpperCase() + c.check.slice(1)), el("td", {}, WHAT[c.measure] || c.measure),
    el("td", { class: "num" }, fmt(c)), el("td", { class: "small muted" }, c.rule),
    el("td", {}, ""));
  r.lastChild.append(el("span", { class: `pill ${c.status}` }, c.status === "pass" ? "Passed" : c.status === "warn" ? "Warning" : "Failed"));
  tb.append(r);
}
t.append(tb);
