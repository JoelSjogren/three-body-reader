#!/usr/bin/env python3
"""Chapter pipeline: EPUB -> per-sentence glosses/translations -> chapterN.js.

Local version of pipeline.ipynb, meant for a machine with ollama and a qwen
model already installed (e.g. the "box" with a GTX 1080).

Usage:
    python3 pipeline.py santi.epub --chapters 1 2 3 --model qwen3:8b

Requires: pypinyin, jieba  (pip install pypinyin jieba)
"""

import argparse
import gzip
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

import jieba
from pypinyin import pinyin as get_pinyin, Style

OLLAMA_URL   = 'http://localhost:11434'
CEDICT_URL   = 'https://www.mdbg.net/chinese/export/cedict/cedict_1_0_ts_utf-8_mdbg.txt.gz'
CEDICT_CACHE = Path.home() / '.cache/cedict/cedict.txt'
HANZI_RE     = re.compile(r'[一-鿿㐀-䶿豈-﫿]')
PUNCT_SET    = set('，。！？；：、“”‘’""\'\'「」（）【】《》〈〉·—…\t\n ')

DIGIT_PINYIN = {'0':'líng','1':'yī','2':'èr','3':'sān','4':'sì','5':'wǔ','6':'liù','7':'qī','8':'bā','9':'jiǔ'}

MODEL = 'qwen3:8b'  # overridden by --model

ANALYZE_PROMPT = """You are analyzing a sentence from the literary science-fiction novel 《三体》 (The Three-Body Problem) by Liu Cixin.

Given the sentence and its word segmentation, return a JSON object with exactly two keys:
- "glosses": an array of {{"seg": <word>, "gloss": <1-4 word English gloss>}} objects,
  one per word segment, in the same order as the input.
  You MUST include every segment — do not skip, merge, or reorder any, including
  grammatical particles. Use these fixed glosses for common particles:
    的 (possessive/attributive) → [poss.]
    了 (perfective aspect) → [perf.]
    着 (progressive aspect) → [prog.]
    过 (experiential aspect) → [exp.]
    地 (adverbial marker) → [adv.]
    得 (resultative marker) → [res.]
  The gloss value is always a JSON string in double quotes — never an unquoted value.
  Example: {{"seg": "的", "gloss": "[poss.]"}} — the brackets are part of the string.
  The glosses must be consistent with the translation (same rendering of idioms and imagery).
- "translation": a single literary English sentence, vivid and atmospheric.
  Preserve Chinese idioms (成语) as evocative images (e.g. 心急如焚 → "heart burning with anxiety").

Word segments ({n} total): {segments}
Sentence: {sentence}

Respond with valid JSON only. No markdown, no explanation.
"""


# ── Ollama setup ───────────────────────────────────────────────────────────────────────

def _server_up():
    try:
        urllib.request.urlopen(f'{OLLAMA_URL}/api/tags', timeout=2)
        return True
    except Exception:
        return False

def ensure_ollama():
    if not _server_up():
        print('Ollama server not reachable; starting `ollama serve`...')
        subprocess.Popen(['ollama', 'serve'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(30):
            if _server_up():
                break
            time.sleep(1)
        else:
            raise RuntimeError('Ollama did not start within 30 s.')
    print('Ollama is running.')

    with urllib.request.urlopen(f'{OLLAMA_URL}/api/tags', timeout=5) as r:
        tags = json.loads(r.read())
    names = {m['name'] for m in tags.get('models', [])}
    if MODEL not in names and f'{MODEL}:latest' not in names:
        print(f'Pulling {MODEL} ...')
        subprocess.run(['ollama', 'pull', MODEL], check=True)
    print('Model ready.')


# ── CC-CEDICT ──────────────────────────────────────────────────────────────────────────

def load_cedict():
    if not CEDICT_CACHE.exists():
        print('Downloading CC-CEDICT...')
        CEDICT_CACHE.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(CEDICT_URL) as r:
            CEDICT_CACHE.write_bytes(gzip.decompress(r.read()))
    cedict = {}
    for line in CEDICT_CACHE.read_text('utf-8').splitlines():
        if line.startswith('#'):
            continue
        m = re.match(r'\S+ (\S+) \[[^\]]+\] /(.+)/', line)
        if not m:
            continue
        simplified, raw_defs = m.group(1), m.group(2).split('/')
        gloss = raw_defs[0]
        for d in raw_defs:
            if not re.match(r'(CL:|variant|see |abbr\.|surname )', d):
                gloss = d
                break
        cedict[simplified] = gloss[:50]
    print(f'  {len(cedict):,} entries loaded.')
    return cedict


# ── EPUB ───────────────────────────────────────────────────────────────────────────────

def find_attr(tag_str, attr):
    m = re.search(rf'\b{attr}="([^"]+)"', tag_str)
    return m.group(1) if m else None

def parse_epub(epub_path, chapter_num):
    with zipfile.ZipFile(epub_path) as zf:
        container = zf.read('META-INF/container.xml').decode('utf-8')
        opf_path  = re.search(r'full-path="([^"]+\.opf)"', container).group(1)
        opf_dir   = str(Path(opf_path).parent)
        opf       = zf.read(opf_path).decode('utf-8')

        def full(href):
            return (opf_dir + '/' + href) if opf_dir != '.' else href

        spine_ids  = re.findall(r'<itemref\s+idref="([^"]+)"', opf)
        id_to_href = {}
        for tag in re.findall(r'<item\b[^>]*/>', opf):
            id_m   = re.search(r'\bid="([^"]+)"', tag)
            href_m = re.search(r'\bhref="([^"]+)"', tag)
            if id_m and href_m:
                id_to_href[id_m.group(1)] = href_m.group(1)
        spine_hrefs = [full(id_to_href[i]) for i in spine_ids if i in id_to_href]

        ncx_item = re.search(r'<item\b[^>]*application/x-dtbncx\+xml[^>]*/>', opf)
        if not ncx_item:
            ncx_item = re.search(r'<item\b[^>]*application/x-dtbncx\+xml[^>]*>', opf)
        ncx_href = find_attr(ncx_item.group(0), 'href')
        ncx = zf.read(full(ncx_href)).decode('utf-8')

        navpoints = re.findall(
            r'<navPoint\b[^>]*>.*?<text>([^<]*)</text>.*?<content\s+src="([^"#]+)',
            ncx, re.DOTALL
        )
        chapter_files = {}
        for label, src in navpoints:
            m = re.match(r'^(\d+)\.', label.strip())
            if m:
                chapter_files[int(m.group(1))] = Path(src.strip()).name

        start_name = chapter_files[chapter_num]
        end_name   = chapter_files.get(chapter_num + 1)

        in_chapter, chapter_hrefs = False, []
        for href in spine_hrefs:
            name = Path(href).name
            if name == start_name:
                in_chapter = True
            if in_chapter:
                if end_name and name == end_name:
                    break
                chapter_hrefs.append(href)

        paragraphs = []
        for href in chapter_hrefs:
            html = zf.read(href).decode('utf-8', errors='replace')
            for raw in re.findall(r'<p[^>]*>(.*?)</p>', html, re.DOTALL):
                text = re.sub(r'<[^>]+>', '', raw)
                text = re.sub(r'\s+', '', text)
                if not text or text == '※※※':
                    continue
                if re.match(r'^\d+[\.。]', text):
                    continue
                paragraphs.append(text)
    return paragraphs


# ── NLP ───────────────────────────────────────────────────────────────────────────────

def split_sentences(text):
    parts = re.split(r'(?<=[。！？])', text)
    sents = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        if sents and all(c in PUNCT_SET for c in p):
            sents[-1] += p  # dangling quote/punct fragment belongs to the previous sentence
        else:
            sents.append(p)
    return sents

def is_punct_token(token):
    return all(c in PUNCT_SET for c in token)

def tokenize(text):
    words, segments = [], []
    for token in jieba.cut(text):
        if not token or not token.strip():
            continue
        if is_punct_token(token):
            for ch in token:
                if ch.strip():
                    words.append({'punct': True, 'chars': [ch]})
        else:
            chars = list(token)
            raw   = get_pinyin(token, style=Style.TONE)
            if len(raw) == len(chars):
                pinyins = [p[0] for p in raw]
            else:
                pinyins = [get_pinyin(ch, style=Style.TONE)[0][0] for ch in chars]
            pinyins = [DIGIT_PINYIN.get(p, p) for p in pinyins]
            words.append({'chars': chars, 'pinyins': pinyins, 'gloss': ''})
            segments.append(token)
    return words, segments


# ── Qwen ───────────────────────────────────────────────────────────────────────────────

# Qwen3 is a thinking model; ask ollama to skip the thinking phase. Some models /
# older ollama versions reject the `think` field, so drop it after the first refusal.
_send_think = True

def _call_ollama(prompt, timeout=600):
    global _send_think
    body = {
        'model':   MODEL,
        'prompt':  prompt,
        'stream':  False,
        'options': {'temperature': 0, 'num_predict': 4096, 'num_ctx': 8192},
    }
    if _send_think:
        body['think'] = False
    req = urllib.request.Request(
        f'{OLLAMA_URL}/api/generate',
        data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            response = json.loads(r.read())['response']
    except urllib.error.HTTPError:
        if not _send_think:
            raise
        _send_think = False
        return _call_ollama(prompt, timeout)
    # If thinking happened anyway, drop the <think> block before parsing.
    response = re.sub(r'<think>.*?</think>', '', response, flags=re.DOTALL)
    return response.strip()

def _parse_json(text):
    text = re.sub(r'^```(?:json)?\s*', '', text.strip())
    text = re.sub(r'\s*```$',          '', text.strip())
    text = text.strip()
    # Replace fullwidth comma used as JSON structural separator
    text = re.sub(r'，(?=\s*")', ',', text)
    # Try strict parse, then whitespace-in-string repair, then first-object extraction
    for attempt in (text, re.sub(r'[\n\r\t]', ' ', text)):
        try:
            return json.loads(attempt)
        except json.JSONDecodeError:
            pass
    obj, _ = json.JSONDecoder().raw_decode(text)
    return obj

# Complete {"seg","gloss"} pairs inside otherwise malformed/truncated output
_PAIR_RE  = re.compile(r'\{\s*"seg"\s*:\s*"((?:[^"\\\\]|\\\\.)*)"\s*,\s*"gloss"\s*:\s*"((?:[^"\\\\]|\\\\.)*)"\s*\}')
_TRANS_RE = re.compile(r'"translation"\s*:\s*"((?:[^"\\\\]|\\\\.)*)"')

def _json_unescape(s):
    try:
        return json.loads(f'"{s}"')
    except ValueError:
        return s

def _recover_partial(raw):
    """Salvage what survives in malformed/truncated Qwen output: every complete
    gloss pair, plus the translation if it made it out before the cutoff."""
    pairs = [{'seg': _json_unescape(s), 'gloss': _json_unescape(g)}
             for s, g in _PAIR_RE.findall(raw)]
    m = _TRANS_RE.search(raw)
    return pairs, (_json_unescape(m.group(1)) if m else None)

COMMON_GLOSSES = {
    # particles & aspect markers
    '的': '(attr.)', '地': '(adv.)', '得': '(comp.)',
    '了': '(perf.)', '着': '(prog.)', '过': '(exp.)',
    '吗': '?', '吧': '(particle)', '呢': '(particle)',
    '啊': '(excl.)', '嘛': '(particle)', '呀': '(excl.)',
    # negation
    '不': 'not', '没': 'not have', '无': 'without',
    # pronouns
    '我': 'I', '你': 'you', '他': 'he', '她': 'she', '它': 'it',
    '我们': 'we', '你们': 'you (pl.)', '他们': 'they', '她们': 'they (f.)',
    '这': 'this', '那': 'that', '哪': 'which',
    '自己': 'oneself',
    # common verbs & words
    '是': 'is', '有': 'have', '在': 'at/in',
    '来': 'come', '去': 'go', '时': 'when/at the time',
    '里': 'inside', '上': 'on/above', '下': 'below',
    '和': 'and', '也': 'also', '都': 'all', '就': 'then/just',
    '还': 'still', '又': 'again', '很': 'very', '最': 'most',
}


def _build_spans(source, tokens):
    """Reconstruct character spans for each token by scanning source left-to-right."""
    pos, spans = 0, []
    for tok in tokens:
        if not tok:
            spans.append(None)
            continue
        idx = source.find(tok, pos)
        if idx == -1:
            idx = source.find(tok)  # fallback: search from start (handles mild reordering)
        if idx == -1:
            spans.append(None)
        else:
            spans.append((idx, idx + len(tok)))
            pos = max(pos, idx + len(tok))
    return spans


def _fallback_gloss(jseg, q_tokens, q_glosses, cedict):
    # 1. Exact-match in Qwen token list (handles displaced spans)
    for q_tok, q_gl in zip(q_tokens, q_glosses):
        if q_tok == jseg and q_gl:
            return q_gl
    # 2. Common-word table
    if jseg in COMMON_GLOSSES:
        return COMMON_GLOSSES[jseg]
    # 3. CC-CEDICT
    return cedict.get(jseg, cedict.get(jseg[0] if jseg else '', ''))


def _align_spans(source, pairs, segments, cedict):
    """Span-based alignment of Qwen glosses to jieba segments.
    Returns (glosses, miss_count) where misses are segments with no recoverable gloss."""
    q_tokens = [p.get('seg', '') for p in pairs]
    q_glosses = [p.get('gloss', '') for p in pairs]
    q_spans = _build_spans(source, q_tokens)
    j_spans = _build_spans(source, segments)
    glosses, misses = [], 0
    for jseg, jspan in zip(segments, j_spans):
        if jspan is None:
            g = _fallback_gloss(jseg, q_tokens, q_glosses, cedict)
            glosses.append(g)
            if not g:
                misses += 1
            continue
        j_start, j_end = jspan
        overlapping = [qg for qs, qg in zip(q_spans, q_glosses)
                       if qs and qs[0] < j_end and qs[1] > j_start]
        if not overlapping:
            g = _fallback_gloss(jseg, q_tokens, q_glosses, cedict)
            glosses.append(g)
            if not g:
                misses += 1
        elif len(overlapping) == 1:
            glosses.append(overlapping[0] or _fallback_gloss(jseg, q_tokens, q_glosses, cedict))
        else:
            combined = ' / '.join(g for g in overlapping if g)
            glosses.append(combined or _fallback_gloss(jseg, q_tokens, q_glosses, cedict))
    return glosses, misses


def analyze_sentence(sent_text, words, segments, cedict):
    """Returns (translation, debug_record)."""
    prompt = ANALYZE_PROMPT.format(
        n=len(segments),
        segments=json.dumps(segments, ensure_ascii=False),
        sentence=sent_text,
    )
    raw = _call_ollama(prompt)

    debug = {
        'source':          sent_text,
        'jieba_segments':  segments,
        'qwen_raw':        raw,
        'qwen_parse_ok':   False,
        'qwen_pairs':      [],
        'qwen_translation': '',
        'alignment_misses': len(segments),
        'n_segments':      len(segments),
    }

    try:
        data        = _parse_json(raw)
        pairs       = data['glosses']
        translation = data['translation']
        debug['qwen_parse_ok']    = True
        debug['qwen_pairs']       = pairs
        debug['qwen_translation'] = translation
        glosses, misses = _align_spans(sent_text, pairs, segments, cedict)
        debug['alignment_misses'] = misses
        if misses:
            print(f'    [{misses}/{len(segments)} fell back]')
    except Exception as e:
        # Salvage partial pairs; _align_spans routes unmatched segments through
        # COMMON_GLOSSES/CC-CEDICT so particles don't get dictionary junk.
        pairs, partial  = _recover_partial(raw)
        glosses, misses = _align_spans(sent_text, pairs, segments, cedict)
        translation = partial or raw  # truncated raw output still helps a little when reading
        debug['qwen_pairs']       = pairs
        debug['qwen_translation'] = partial or ''
        debug['alignment_misses'] = misses
        print(f'    [JSON parse failed: {e}; recovered {len(pairs)} pairs, '
              f'{misses}/{len(segments)} fell back]')

    gi = 0
    for w in words:
        if not w.get('punct'):
            w['gloss'] = glosses[gi] if gi < len(glosses) else cedict.get(''.join(w['chars']), '')
            gi += 1

    return translation, debug


# ── JS output ──────────────────────────────────────────────────────────────────────────

def _js_str(s):
    return s.replace('\\', '\\\\').replace("'", "\\'")

def render_js(paragraphs_data, var_name):
    lines = [f'window.{var_name} = [']
    for para in paragraphs_data:
        lines.append('  { sentences: [')
        for sent in para:
            translation = sent['translation'].replace('`', '\\`')
            lines.append('    {')
            lines.append(f'      translation: `{translation}`,')
            lines.append('      words: [')
            for w in sent['words']:
                if w.get('punct'):
                    lines.append(f"        {{ punct: true, chars: ['{_js_str(w['chars'][0])}'] }},")
                else:
                    chars   = ', '.join(f"'{_js_str(c)}'" for c in w['chars'])
                    pinyins = ', '.join(f"'{_js_str(p)}'" for p in w['pinyins'])
                    gloss   = _js_str(w['gloss'])
                    lines.append(f"        {{ chars: [{chars}], pinyins: [{pinyins}], gloss: '{gloss}' }},")
            lines.append('      ],')
            lines.append('    },')
        lines.append('  ] },')
    lines.append('];')
    return '\n'.join(lines)


def warmup():
    print(f'Warming up {MODEL}...')
    print(f'  Ready: {_call_ollama("Say hello in one word.")!r}')


# ── Main ───────────────────────────────────────────────────────────────────────────────

def main():
    global MODEL
    ap = argparse.ArgumentParser(description='EPUB chapter -> annotated chapterN.js via ollama')
    ap.add_argument('epub', help='path to the EPUB file')
    ap.add_argument('--chapters', type=int, nargs='+', default=[1],
                    help='chapter numbers to process (default: 1)')
    ap.add_argument('--model', default=MODEL,
                    help=f'ollama model name (default: {MODEL})')
    ap.add_argument('--out-dir', default='.',
                    help='directory for chapterN.js / chapterN-debug.json (default: .)')
    args = ap.parse_args()

    MODEL = args.model
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    ensure_ollama()
    cedict = load_cedict()
    warmup()

    for chapter_num in args.chapters:
        print(f'Extracting chapter {chapter_num} from {args.epub}...')
        raw_paragraphs = parse_epub(args.epub, chapter_num)
        print(f'  {len(raw_paragraphs)} paragraphs.')

        paragraphs_data = []
        debug_records   = []   # flat list of per-sentence debug dicts
        total_segs = total_misses = 0

        for pi, para_text in enumerate(raw_paragraphs):
            sentences  = split_sentences(para_text)
            para_sents = []
            for si, sent_text in enumerate(sentences):
                print(f'  [{pi+1}/{len(raw_paragraphs)}] s{si+1}: {sent_text[:50]}', flush=True)
                words, segments = tokenize(sent_text)
                translation, debug = analyze_sentence(sent_text, words, segments, cedict)
                debug['para_idx'] = pi
                debug['sent_idx'] = si
                print(f'    → {translation[:70]}', flush=True)
                para_sents.append({'translation': translation, 'words': words})
                debug_records.append(debug)
                total_segs   += debug['n_segments']
                total_misses += debug['alignment_misses']
            paragraphs_data.append(para_sents)

        print(f'\nChapter {chapter_num} done. Overall fallback: {total_misses}/{total_segs} '
              f'({100*total_misses/max(total_segs,1):.1f}%)')

        output_js    = out_dir / f'chapter{chapter_num}.js'
        output_debug = out_dir / f'chapter{chapter_num}-debug.json'
        output_js.write_text(render_js(paragraphs_data, f'CHAPTER{chapter_num}'), encoding='utf-8')
        output_debug.write_text(json.dumps(debug_records, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'Wrote {output_js} and {output_debug}.')


if __name__ == '__main__':
    main()
