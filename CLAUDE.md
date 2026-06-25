# Three Body Reader — Agent Notes

## Constraints

- **Never commit `example-data/`**. It holds raw ebook files used for local
  experimentation only.
- HTML files must work via `file://` in Chrome (no dev server). Avoid ES
  modules (`import`/`export`) and any fetch of relative paths until a server
  is added.

## EPUB structure

EPUBs are ZIP archives. The Three Body Problem file unpacks like this:

```
EPUB/content.opf          — manifest + reading order (spine)
EPUB/index_split_000.html — front matter / TOC
EPUB/index_split_006.html — Chapter 1 starts here
EPUB/index_split_007.html — Chapter 1 continues (larger file)
...
```

To extract text from a specific file without unpacking the whole archive:

```bash
unzip -p example-data/ThreeBodyProblem.epub EPUB/index_split_006.html \
  | python3 -c "
import sys, re
html = sys.stdin.read()
text = re.sub(r'<[^>]+>', '', html)
print(text)
"
```

## CSS layout for the 4-row sentence display

Each of rows (a)/(b)/(c) is a separate `<div>` with:

```css
display: grid;
grid-template-columns: repeat(N, 2.6rem);  /* N = number of characters */
```

Because all three grids use the same column definition, their columns align
visually when stacked. Row (c) word cells span multiple columns with inline
`style="grid-column: span 2"` (or whatever the word length is).

Row (d) is a plain block below the grids — no grid needed.

## Current files

| File | Purpose |
|------|---------|
| `poc.html` | Hard-coded proof of concept; open directly in Chrome |
| `example-data/Page1.txt` | First page of chapter 1, plain text, for reference |
