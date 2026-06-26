# Three Body Reader

## Important agent instructions

Do not commit the data in "example-data", but feel free to add stuff there during experimentation.

## Goals

- Web app that runs on both phone and laptop
- Read local Chinese ebook files in EPUB format
- Runs entirely client-side, hostable on GitHub Pages or similar static hosts
- Each sentence will be displayed in 4 ways on top of each other: (a) original chinese, (b) pinyin [aligned with the chinese characters], (c) [segmentation and] translation of each word into english [also aligned with the first two rows], (d) [somewhat literal] translation of the whole sentence into english.
- The user can click an english word to hide it and all its occurences throughout the book. The user can click the empty space to reveal the english word again. The user can also click pinyin to hide/show it in a similar way.
- The user can toggle whether to color chinese characters and words by their frequency of appearance either in Chinese at large or statistically in the current book.
- The user can ask for the whole sentence of pinyin to be read at slow or medium pace, and the color of the pinyin syllables will flash through in a different color as the audio progresses.

## Files

| File | Purpose |
|------|---------|
| `poc.html` | Hard-coded proof of concept for the 4-row CSS grid layout (single sentence) |
| `poc2.html` | Same layout but with line-wrapping; uses flex word-blocks instead of a single grid |
| `poc3.html` | Adds TTS via the Web Speech API (single sentence, slow rate) |
| `poc4.html` | Multiple sentences loaded from an external data file; per-sentence TTS buttons |
| `poc5.html` | Adds hover highlight: mousing over a character turns all occurrences red |
| `poc6.html` | Adds click-to-fade on (b) and (c); faded state persisted in `localStorage` |
| `example-data/sentences-poc4.js` | Sentence data for poc4–poc6 (not committed) |

## Technical notes

### EPUB structure
- EPUB files are ZIP archives; `unzip -p` extracts a named entry to stdout.
- Chapter 1 content lives in `EPUB/index_split_006.html` inside the archive.
- Python strips HTML tags with regex and normalises whitespace between paragraphs.
- Reading order and chapter structure are declared in `EPUB/content.opf`.

### Layout (poc2+)
- Each word is a `flex-column` block containing rows (a), (b), (c) stacked vertically.
- The sentence container is `display: flex; flex-wrap: wrap`, so word-blocks wrap as a unit — rows (a)/(b)/(c) always stay aligned with each other.
- `row-gap` on the container adds breathing room between wrapped lines.
- All files work via `file://` in Chrome: no ES modules, no `fetch()` of relative paths. External data is loaded via `<script src>` which works over `file://`.

### TTS (poc3+)
- Uses the browser's built-in Web Speech API (`SpeechSynthesisUtterance`), no library needed.
- `onboundary` events carry a `charIndex` mapped back to word-blocks for syllable highlighting.
- On Linux, Chrome's espeak backend does not fire `onboundary` events; audio still works.

### Interactivity (poc5+)
- **Hover highlight (poc5):** character spans are grouped by character into a `Map`; mouseenter/mouseleave adds/removes a CSS class on all spans in the group.
- **Click-to-fade (poc6):** two `localStorage` sets — `faded-pinyin` (keyed by individual character, e.g. `"的"`) and `faded-gloss` (keyed by joined word chars, e.g. `"大楼"`). Clicking a pinyin syllable fades that character's pinyin everywhere; clicking a gloss fades that word's gloss everywhere. Row (a) has no click interaction.
