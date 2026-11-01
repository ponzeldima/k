// Попередній перегляд пояснювальної записки: Markdown-розділи -> HTML з формулами KaTeX ->
// PDF через headless Chrome. Оформлення наближене до вимог методички (ДСТУ 3008): Times New Roman
// 14 пт, інтервал 1,5, абзац 1,25 см, поля 2 см, підпис рисунка знизу посередині, таблиці – згори.
//
// Підтримується: заголовки # / ## / ###, абзаци, таблиці (підпис «Таблиця N.M – …» абзацом перед
// таблицею), рисунки ![Рисунок N.M – назва](шлях){width=70%}, формули $…$ і $$…$$ (номер – \tag{N.M}),
// переліки «- » і «1) », блоки коду ```…```, посилання на джерела [@ключ] і [@ключ, с. 63; @ключ2].
//
// Запуск: node preview.mjs вихід.html джерела.txt розділ1.md розділ2.md …
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { __katexFactory } from "./katex/katex_mod.mjs";

const kx = __katexFactory();
const katex = kx.default ?? kx;
const here = path.dirname(fileURLToPath(import.meta.url));
const [, , htmlPath, sourcesPath, ...mdPaths] = process.argv;

// джерела: рядки «ключ: бібліографічний опис»; номери – за порядком першого посилання в тексті
const sources = new Map();
for (const line of fs.readFileSync(sourcesPath, "utf8").split(/\r?\n/)) {
  const m = line.match(/^([\w-]+):\s+(.+)$/);
  if (m) sources.set(m[1], m[2]);
}
const order = [];
function citeNo(key) {
  if (!sources.has(key)) throw new Error(`Невідоме джерело: ${key}`);
  if (!order.includes(key)) order.push(key);
  return order.indexOf(key) + 1;
}

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const tex = (s, display) =>
  katex.renderToString(s, { displayMode: display, strict: "ignore", throwOnError: true, output: "html" });

function inline(s) {
  const keep = [];
  const hold = (html) => `\u0000${keep.push(html) - 1}\u0000`;
  s = s.replace(/\$([^$]+?)\$/g, (_, m) => hold(tex(m, false)));
  s = s.replace(/`([^`]+)`/g, (_, c) => hold(`<code>${esc(c)}</code>`));
  s = s.replace(/\[(@[^\]]+)\]/g, (_, body) =>
    hold("[" + body.split(/;\s*/).map((part) => {
      const m = part.match(/^@([\w-]+)(.*)$/);
      return `${citeNo(m[1])}${esc(m[2])}`;
    }).join("; ") + "]"));
  s = s.replace(/(\d) — /g, "$1 — ");
  s = esc(s);
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/(^|[^*])\*([^*\s][^*]*?)\*(?!\*)/g, "$1<em>$2</em>");
  return s.replace(/\u0000(\d+)\u0000/g, (_, i) => keep[+i]);
}

const cells = (row) => row.trim().replace(/^\|/, "").replace(/\|$/, "").split("|").map((c) => c.trim());
const isBlockStart = (l) => /^(#{1,3}\s|\$\$|\||!\[|- |\d+\) |```)/.test(l);

function convert(mdPath, out) {
  const src = fs.readFileSync(mdPath, "utf8").replace(/\r\n/g, "\n");
  const baseDir = path.dirname(path.resolve(mdPath));
  const lines = src.split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const inc = line.match(/^@include\s+(\S+)\s*$/);
    if (inc) {  // вставка таблиці, побудованої скриптом з результатів
      const extra = fs.readFileSync(path.resolve(baseDir, inc[1]), "utf8").replace(/\r\n/g, "\n").split("\n");
      lines.splice(i, 1, ...extra);
      continue;
    }
    if (!line.trim() || /^<!--.*-->\s*$/.test(line)) { i++; continue; }

    if (line.startsWith("```")) {
      const buf = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) buf.push(lines[i++]);
      i++;
      out.push(`<pre>${esc(buf.join("\n"))}</pre>`);
      continue;
    }
    if (line.startsWith("$$")) {
      const buf = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("$$")) buf.push(lines[i++]);
      i++;
      out.push(`<div class="dm">${tex(buf.join("\n"), true)}</div>`);
      continue;
    }
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h) { out.push(`<h${h[1].length}>${inline(h[2])}</h${h[1].length}>`); i++; continue; }

    const img = line.match(/^!\[([^\]]*)\]\(([^)]+)\)(?:\{width=(\d+%)\})?\s*$/);
    if (img) {
      const url = pathToFileURL(path.resolve(baseDir, img[2])).href;
      const style = img[3] ? ` style="width:${img[3]}"` : "";
      out.push(`<figure><img src="${url}"${style}><figcaption>${inline(img[1])}</figcaption></figure>`);
      i++;
      continue;
    }
    if (line.startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].startsWith("|")) rows.push(lines[i++]);
      const align = cells(rows[1]).map((c) => (c.startsWith(":") && c.endsWith(":") ? "center"
        : c.endsWith(":") ? "right" : "left"));
      const tr = (r, tag) =>
        "<tr>" + cells(r).map((c, k) => `<${tag} style="text-align:${align[k]}">${inline(c)}</${tag}>`).join("") + "</tr>";
      const keep = rows.length <= 8 && rows.join("").length < 700 ? ' class="keep"' : "";
      out.push(`<table${keep}><thead>${tr(rows[0], "th")}</thead><tbody>${rows.slice(2).map((r) => tr(r, "td")).join("")}</tbody></table>`);
      continue;
    }
    const li = line.match(/^(- |\d+\) )/);
    if (li) {
      const tag = li[1] === "- " ? "ul" : "ol";
      const items = [];
      while (i < lines.length && /^(- |\d+\) )/.test(lines[i])) {
        let item = lines[i++].replace(/^(- |\d+\) )/, "");
        while (i < lines.length && /^ {2,}\S/.test(lines[i])) item += " " + lines[i++].trim();
        items.push(item);
      }
      out.push(`<${tag}>${items.map((t) => `<li>${inline(t)}</li>`).join("")}</${tag}>`);
      continue;
    }
    const buf = [line];
    i++;
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) buf.push(lines[i++]);
    const text = buf.join(" ");
    const cls = /^Таблиця \d/.test(text) ? ' class="tcap"'
      : /^Продовження таблиці/.test(text) ? ' class="tcap"'
      : /:$/.test(text) ? ' class="lead"' : "";
    out.push(`<p${cls}>${inline(text)}</p>`);
  }
}

const out = [];
for (const p of mdPaths) convert(p, out);
if (order.length) {
  out.push("<h1>СПИСОК ВИКОРИСТАНИХ ДЖЕРЕЛ</h1>");
  out.push(`<ol class="refs">${order.map((k) => `<li>${esc(sources.get(k))}</li>`).join("")}</ol>`);
}

const css = pathToFileURL(path.join(here, "katex", "katex.min.css")).href;
const html = `<!doctype html>
<html lang="uk"><head><meta charset="utf-8"><title>Пояснювальна записка – попередній перегляд</title>
<link rel="stylesheet" href="${css}">
<style>
@page { size: A4; margin: 20mm 20mm 20mm 20mm; }
body { font-family: "Times New Roman", serif; font-size: 14pt; line-height: 1.5; color: #000; margin: 0; }
h1 { font-size: 14pt; font-weight: bold; text-align: center; text-transform: uppercase; margin: 0 0 12pt;
     break-before: page; break-after: avoid; }
h1:first-child { break-before: auto; }
h2, h3 { font-size: 14pt; font-weight: bold; text-indent: 1.25cm; margin: 10pt 0 4pt; break-after: avoid; }
p { margin: 0; text-indent: 1.25cm; text-align: justify; }
p.tcap { text-indent: 0; text-align: left; margin-top: 8pt; break-after: avoid; }
p.lead { break-after: avoid; }
figure { margin: 8pt 0 8pt; text-align: center; break-inside: avoid; }
figure img { max-width: 100%; max-height: 210mm; }
figcaption { text-align: center; margin-top: 4pt; }
table { border-collapse: collapse; width: 100%; margin: 2pt 0 8pt; font-size: 12pt; line-height: 1.15; }
th, td { border: 0.6pt solid #000; padding: 2pt 4pt; vertical-align: middle; }
th { font-weight: normal; }
tr { break-inside: avoid; }
table.keep { break-inside: avoid; }
.dm { margin: 2pt 0 4pt; break-inside: avoid; }
.katex { font-size: 1.05em; }
.katex-display { margin: 0.2em 0; }
code { font-family: "Courier New", monospace; font-size: 12pt; }
pre { font-family: "Courier New", monospace; font-size: 10pt; line-height: 1.2; margin: 4pt 0 8pt;
      white-space: pre-wrap; break-inside: avoid; }
ul, ol { margin: 0; padding-left: 0; list-style: none; }
li { text-indent: 1.25cm; text-align: justify; }
ul > li::before { content: "– "; }
ol { counter-reset: item; }
ol > li { counter-increment: item; }
ol > li::before { content: counter(item) ") "; }
ol.refs > li::before { content: counter(item) ". "; }
</style></head><body>
${out.join("\n")}
</body></html>
`;
fs.writeFileSync(htmlPath, html, "utf8");
console.log("ok", out.length, "blocks;", order.length, "sources cited");
