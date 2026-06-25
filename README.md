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

## Technical knowledge involved in the implementation

### Page1.txt
- EPUB files are ZIP archives; `unzip -p` extracts a named entry to stdout.
- Chapter 1 content lives in `EPUB/index_split_006.html` inside the archive.
- Python strips HTML tags with regex and normalises whitespace between paragraphs.
- Reading order and chapter structure are declared in `EPUB/content.opf`.

### poc.html
- CSS grid with `repeat(14, 2.6rem)` gives one fixed-width column per character.
- Rows (a)/(b)/(c) are separate grids with identical column defs so they align.
- Multi-character words in row (c) use `grid-column: span N` for word grouping.
- No server needed: the file uses no ES modules, so `file://` protocol works.

## Current state

Update this section as we go along and implement the project. For now nothing exists yet, so here's some TODOs:

- Try extracting the first page of the first chapter of example-data/ThreeBodyProblem.epub and store it as Page1.txt
- Make a basic poc.html that I can just open directly in chrome without needing to start a server for now. Put a sample chinese sentence in it and show the (a,b,c,d) versions of it as a proof of concept. No need to actually process anything in poc.html at this stage -- just hard code all forms of the example data.