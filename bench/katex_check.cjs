// Check that every predicted equation in a results file parses in KaTeX.
// Uses the KaTeX build bundled with snipmd for the preview page.
//   node bench/katex_check.cjs bench/results/accuracy-mlx-x2.json
const path = require("path");
const katex = require(path.join(__dirname, "..", "src", "snipmd", "assets", "katex", "katex.min.js"));
const file = process.argv[2] || path.join(__dirname, "results", "accuracy-mlx-x2.json");
const rows = require(path.resolve(file)).rows;
let ok = 0;
for (const row of rows) {
  try {
    katex.renderToString(row.pred, { throwOnError: true, displayMode: true });
    ok += 1;
  } catch (err) {
    console.log(`eq${String(row.id).padStart(2, "0")}: ${err.message}`);
  }
}
console.log(`${ok}/${rows.length} parse in KaTeX ${katex.version}`);
