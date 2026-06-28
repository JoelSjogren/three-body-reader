#!/usr/bin/env python3
"""
charstats.py -- extract CJK character frequencies from an EPUB.
Usage: python charstats.py [path/to/book.epub]
Output: charstats.js in the current directory, loaded by poc9.html as window.CHARSTATS.
"""
import sys, zipfile, re, json
from collections import Counter
from pathlib import Path


def is_cjk(ch):
    cp = ord(ch)
    return (0x4E00 <= cp <= 0x9FFF or   # CJK Unified Ideographs (main block)
            0x3400 <= cp <= 0x4DBF or   # CJK Extension A
            0x20000 <= cp <= 0x2A6DF)   # CJK Extension B


def extract_text(epub_path):
    with zipfile.ZipFile(epub_path) as z:
        container = z.read('META-INF/container.xml').decode('utf-8')
        opf_path = re.search(r'full-path="([^"]+\.opf)"', container).group(1)
        opf = z.read(opf_path).decode('utf-8')

        # Map item id -> href from manifest (attr order-independent)
        items = {}
        for tag in re.findall(r'<item\b[^>]*/>', opf):
            id_m   = re.search(r'\bid="([^"]+)"',   tag)
            href_m = re.search(r'\bhref="([^"]+)"', tag)
            if id_m and href_m:
                items[id_m.group(1)] = href_m.group(1)
        # Spine reading order
        spine_ids = re.findall(r'<itemref\b[^>]*\bidref="([^"]+)"', opf)

        base = str(Path(opf_path).parent)
        chunks = []
        for iid in spine_ids:
            href = items.get(iid, '')
            if not href:
                continue
            full = (base + '/' + href).lstrip('/')
            try:
                raw = z.read(full).decode('utf-8', errors='replace')
                chunks.append(re.sub(r'<[^>]+>', '', raw))
            except KeyError:
                pass
    return ''.join(chunks)


def main():
    epub_path = sys.argv[1] if len(sys.argv) > 1 else 'example-data/ThreeBodyProblem.epub'
    print(f'Reading {epub_path} ...')
    text = extract_text(epub_path)
    freq = Counter(ch for ch in text if is_cjk(ch))
    sorted_pairs = sorted(freq.items(), key=lambda x: -x[1])
    print(f'{len(sorted_pairs)} unique CJK characters, {sum(freq.values())} total occurrences')

    # Object keys in insertion order -> rank is implicit (first entry = rank 1)
    data = {ch: count for ch, count in sorted_pairs}
    out = 'window.CHARSTATS=' + json.dumps(data, ensure_ascii=False, separators=(',', ':')) + ';\n'

    out_path = Path(__file__).parent / 'charstats.js'
    out_path.write_text(out, encoding='utf-8')
    print(f'Written {out_path} ({out_path.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
