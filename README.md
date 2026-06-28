# Three Body Reader

A Chinese language learning reader for 《三体》. Each sentence is shown in 4 rows:
(a) original Chinese, (b) per-character pinyin, (c) per-word English gloss, (d) full translation.

## Workflow

Run `pipeline.ipynb` in Google Colab (Runtime → T4 GPU) to process the EPUB and produce a
`chapterN.js` data file. The notebook prompts for the EPUB upload first, then installs
dependencies, starts Ollama, and runs Qwen2.5:14b over every sentence. When done, it downloads
the JS file. Open `poc9.html` in Chrome, click "Choose file…", and select the downloaded `.js`.
Everything runs client-side; no server is needed.

## Files

| File | Purpose |
|------|---------|
| `poc1.html` | Hard-coded proof of concept — single sentence, 4-row layout |
| `poc7.html` | Paragraph navigation with hardcoded chapter 1 data |
| `poc8.html` | Full reader: file picker, paragraph navigation, TTS, click-to-fade |
| `poc9.html` | poc8 + pinyin/gloss sliders, frequency coloring, vocabulary glossary (known chars/words tabs, drag-to-reorder, groups, multi-gloss chips, TTS per word) |
| `pipeline.ipynb` | Colab notebook: EPUB → `chapterN.js` via jieba + pypinyin + Qwen2.5:14b |
| `charstats.py` | Extracts book-wide CJK character frequencies from the EPUB; outputs `charstats.js` |

## Goals

- [ ] Web app that runs on both phone and laptop — laptop works; phone blocked: iOS forbids
      opening `file://` URLs in the browser entirely (unrelated to the file picker mechanism)
- [~] Read local EPUB files — pipeline processes the EPUB; next step is (a)+(b)-only mode
      (pypinyin + jieba, no Qwen) so the EPUB can be loaded with a much simpler pipeline
- [ ] Hostable on GitHub Pages — reader HTML is static; hosting of book data is not planned
- [x] 4-row sentence display (a/b/c/d) with character- and word-level alignment
- [x] Click to hide/show pinyin and English glosses; faded state persisted in `localStorage`
- [x] Color characters by frequency — sigmoidal log-scale slider in poc9; slider middle = rank 100
- [x] Vocabulary glossary — known chars/words with drag-to-reorder, groups, multi-gloss chips
- [~] TTS with syllable highlighting — audio works; syllable sync on hold (no reliable
      cross-platform `onboundary` support in browser speech APIs)

## Technical notes

### EPUB pipeline
- jieba segments Chinese text into words; pypinyin provides tone-marked pinyin per character.
- CC-CEDICT (~121 k entries) is downloaded as an offline fallback gloss dictionary.
- Qwen2.5:14b is called once per sentence, returning both (c) word glosses and (d) translation
  in one JSON response so the two rows agree on idioms (e.g. 心急如焚 → "heart burning").
- Output: `window.CHAPTERX = [{sentences: [{translation, words: [{chars, pinyins, gloss}]}]}]`.

### TODO
- Some source sentences are very long (e.g. paragraph 3, sentence 1 of chapter 1). The English
  translation sometimes contains internal `.`, `;`, or `...` that suggest natural split points. It may be
  possible to break these at matching Chinese punctuation (。；), but only when the English
  punctuation position aligns with a Chinese clause boundary — otherwise the word/gloss arrays
  would no longer correspond to a single coherent sentence.
- Allow initiating a drag of a character into a tab, starting from either of "known chars", "known
  words" (then dragging the whole word instead), "para", "chapter", "book".

### Handling imperfect Qwen output
- Qwen is asked for `{"glosses": [{"seg": word, "gloss": "…"}, …], "translation": "…"}`.
- Count mismatches (Qwen merging or splitting jieba segments) are resolved by greedy
  left-to-right alignment with lookahead: only unmatched segments fall back to CC-CEDICT.
- JSON parse failures keep Qwen's translation but substitute CC-CEDICT for all glosses.
- Common structural particles (的, 了, 着 …) are given fixed shorthand glosses ([poss.] etc.)
  via prompt instruction to avoid verbose CC-CEDICT entries.

### Reader (poc9.html)
- Data loaded via `<input type="file">` + `FileReader` + `eval()` — works over `file://`.
- Each word is a `display: flex; flex-direction: column` block; the sentence container uses
  `flex-wrap: wrap` so word-blocks (all three rows) wrap together.
- TTS via Web Speech API; `onboundary` events drive per-syllable highlight (Linux: audio only).
- Known state: `fadedCharsOrder`/`fadedWordsOrder` (insertion-order arrays) + `fadedChar/WordGroups` (Maps, char→groupName) + Sets for O(1) lookup; keyed by Chinese string throughout.
- `virtualKnown`/`virtualKnownWords`: uncommitted working copies while on a known tab, flushed on tab-leave — preserves insertion order when toggling items.
- Paragraph position persists in `localStorage['paragraph-index']` and is restored on load.

### EPUB structure
- EPUBs are ZIP archives; reading order and file paths come from the OPF manifest.
- Chapter boundaries are located via navPoint labels in the NCX table of contents.
