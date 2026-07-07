# Three Body Reader — Agent Notes

- **This file and README.md must be disjoint**: information belongs in one or the other, never both.
- **This file ≤ 20 lines, README ≤ 80 lines**: keep both within these limits.
- **Never commit `example-data/`**: it holds raw ebook and generated data files.
- **HTML files must work via `file://` in Chrome**: no ES modules, no `fetch()` of relative paths.
  Data is loaded via `<script src>` or `<input type="file">` + `FileReader` + `eval()`.
- **`pipeline.ipynb`**: the upload cell must stay first (step 1) to avoid Colab timeout.
  Edit pipeline logic directly in the notebook; there are no separate .py source files.
  Outputs both `chapterN.js` and `chapterN-debug.json` (per-sentence Qwen raw output,
  parse status, alignment misses). Never commit these outputs.
- **`align-debug.py`**: offline alignment iteration tool — reads `chapter1-debug.json` and
  benchmarks the alignment algorithm without re-running Qwen. Logbook at end of file tracks changes.
