"""
align-debug.py
==============
Offline iteration tool for the alignment algorithm.

Loads chapter1-debug.json produced by pipeline.ipynb and compares
the old greedy-lookahead algorithm against a new span-based algorithm.
Run as:
    python align-debug.py [chapter1-debug.json]
"""

import json
import re
import sys
from pathlib import Path
from collections import Counter


def try_parse_qwen(raw):
    """Try progressively more lenient parses; return glosses list or None."""
    for attempt in (raw, re.sub(r'[\n\r\t]', ' ', raw)):
        try:
            obj = json.loads(attempt)
            return obj.get('glosses', [])
        except json.JSONDecodeError:
            pass
    # Last resort: decode first valid JSON object (handles trailing garbage)
    try:
        obj, _ = json.JSONDecoder().raw_decode(raw)
        return obj.get('glosses', [])
    except (json.JSONDecodeError, AttributeError):
        return None

# ── load ──────────────────────────────────────────────────────────────────────

def load_debug(path):
    data = json.loads(Path(path).read_text('utf-8'))
    print(f'Loaded {len(data)} sentences from {path}')
    return data


# ── OLD algorithm (greedy lookahead, same as pipeline.ipynb) ──────────────────

def align_greedy(qwen_pairs, jieba_segs):
    """Returns (glosses, miss_count). Glosses are '' where fallback would occur."""
    glosses, misses = [], 0
    j = 0
    for seg in jieba_segs:
        if j < len(qwen_pairs) and qwen_pairs[j].get('seg') == seg:
            glosses.append(qwen_pairs[j].get('gloss', ''))
            j += 1
        else:
            found = False
            for skip in range(1, 4):
                if j + skip < len(qwen_pairs) and qwen_pairs[j + skip].get('seg') == seg:
                    glosses.append(qwen_pairs[j + skip].get('gloss', ''))
                    j = j + skip + 1
                    found = True
                    break
            if not found:
                glosses.append('')
                misses += 1
    return glosses, misses


# ── NEW algorithm (character-span based) ──────────────────────────────────────

# Fallback glosses for common words that Qwen sometimes truncates or leaves blank.
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
    # content words seen as tail truncations in chapter 1
    '脚步': 'footsteps', '双眼': 'both eyes',
}


def _fallback_gloss(jseg, q_tokens, q_glosses):
    """Last-resort gloss when span alignment produces nothing."""
    # 1. Exact segment match in Qwen list (handles displaced spans)
    for q_tok, q_gl in zip(q_tokens, q_glosses):
        if q_tok == jseg and q_gl:
            return q_gl
    # 2. Common-word table
    return COMMON_GLOSSES.get(jseg, '')


def _build_spans(source, tokens):
    """
    Reconstruct character spans for each token by scanning source left-to-right.
    Returns list of (start, end) or None if token not found.
    Handles the case where a token cannot be located (Qwen wrote different chars).
    """
    pos = 0
    spans = []
    for tok in tokens:
        if not tok:
            spans.append(None)
            continue
        idx = source.find(tok, pos)
        if idx == -1:
            # Try from position 0 as fallback (handles mild reordering)
            idx = source.find(tok)
        if idx == -1:
            spans.append(None)
        else:
            spans.append((idx, idx + len(tok)))
            pos = max(pos, idx + len(tok))
    return spans


def align_spans(source, qwen_pairs, jieba_segs):
    """
    Span-based alignment.
    1. Reconstruct char spans for Qwen segments within source.
    2. Reconstruct char spans for jieba segments within source.
    3. For each jieba span, collect all overlapping Qwen spans → take their gloss.
    Returns (glosses, miss_count).
    """
    q_tokens = [p.get('seg', '') for p in qwen_pairs]
    q_glosses = [p.get('gloss', '') for p in qwen_pairs]
    q_spans = _build_spans(source, q_tokens)
    j_spans = _build_spans(source, jieba_segs)

    glosses = []
    misses = 0

    for jseg, jspan in zip(jieba_segs, j_spans):
        if jspan is None:
            glosses.append('')
            misses += 1
            continue

        j_start, j_end = jspan
        overlapping = []
        for qspan, qgloss in zip(q_spans, q_glosses):
            if qspan is None:
                continue
            q_start, q_end = qspan
            if q_start < j_end and q_end > j_start:
                overlapping.append(qgloss)

        if not overlapping:
            g = _fallback_gloss(jseg, q_tokens, q_glosses)
            glosses.append(g)
            if not g:
                misses += 1
        elif len(overlapping) == 1:
            # Span found but gloss may be empty → try fallback for quality
            glosses.append(overlapping[0] or _fallback_gloss(jseg, q_tokens, q_glosses))
        else:
            combined = ' / '.join(g for g in overlapping if g)
            glosses.append(combined or _fallback_gloss(jseg, q_tokens, q_glosses))

    return glosses, misses


# ── analysis ──────────────────────────────────────────────────────────────────

def analyse(records):
    old_total = new_total = total_segs = 0
    old_by_para = Counter()
    new_by_para = Counter()
    segs_by_para = Counter()

    parse_failures = 0
    span_locate_failures = Counter()  # how often a Qwen segment can't be found

    WORST = []   # (old_miss_rate - new_miss_rate, record) for improvement examples
    FIXED = []   # sentences where new is better
    WORSE = []   # sentences where new is worse

    for rec in records:
        pi = rec['para_idx']
        source = rec['source']
        segs = rec['jieba_segments']
        pairs = rec.get('qwen_pairs', [])
        parse_ok = rec.get('qwen_parse_ok', False)

        n = rec['n_segments']
        total_segs += n
        segs_by_para[pi] += n

        if not parse_ok:
            recovered = try_parse_qwen(rec.get('qwen_raw', ''))
            if recovered is not None:
                pairs = recovered
                _, old_misses = align_greedy(pairs, segs)
                _, new_misses = align_spans(source, pairs, segs)
            else:
                parse_failures += 1
                old_misses = n
                new_misses = n
        else:
            _, old_misses = align_greedy(pairs, segs)
            _, new_misses = align_spans(source, pairs, segs)

            # Count Qwen tokens that can't be found in source (span locate failures)
            q_tokens = [p.get('seg', '') for p in pairs]
            spans = _build_spans(source, q_tokens)
            missing = sum(1 for s in spans if s is None)
            if missing:
                span_locate_failures[pi] += missing

        old_total += old_misses
        new_total += new_misses
        old_by_para[pi] += old_misses
        new_by_para[pi] += new_misses

        delta = old_misses - new_misses
        if delta > 0:
            FIXED.append((delta, rec))
        elif delta < 0:
            WORSE.append((-delta, rec))

    paras = sorted(set(r['para_idx'] for r in records))

    print('\n=== Paragraph-level fallback ===')
    print(f'{"Para":>5}  {"segs":>5}  {"old miss":>8}  {"old%":>5}  {"new miss":>8}  {"new%":>5}  {"delta":>6}')
    for pi in paras:
        s = segs_by_para[pi]
        o = old_by_para[pi]
        n = new_by_para[pi]
        d = o - n
        print(f'{pi+1:>5}  {s:>5}  {o:>8}  {100*o/max(s,1):>5.1f}  {n:>8}  {100*n/max(s,1):>5.1f}  {d:>+6}')

    print(f'\n=== Overall ===')
    print(f'  Segments total : {total_segs}')
    print(f'  Parse failures : {parse_failures} sentences')
    print(f'  Old fallback   : {old_total}/{total_segs} = {100*old_total/max(total_segs,1):.1f}%')
    print(f'  New fallback   : {new_total}/{total_segs} = {100*new_total/max(total_segs,1):.1f}%')
    print(f'  Improvement    : {old_total - new_total} fewer misses ({(old_total - new_total)/max(old_total,1)*100:.1f}% reduction)')

    if span_locate_failures:
        total_unfindable = sum(span_locate_failures.values())
        print(f'\n  Qwen tokens not found in source: {total_unfindable} '
              f'(these are irreducible span failures)')
        print(f'  Affects paras: {sorted(k+1 for k in span_locate_failures)}')

    print(f'\n=== Sentences improved by span alignment (top 10) ===')
    for delta, rec in sorted(FIXED, key=lambda x: x[0], reverse=True)[:10]:
        pi, si = rec['para_idx'], rec['sent_idx']
        source = rec['source']
        print(f'  para {pi+1} s{si+1}: -{delta} misses | {source[:60]}')

    if WORSE:
        print(f'\n=== Sentences made WORSE by span alignment ({len(WORSE)} cases) ===')
        for delta, rec in sorted(WORSE, key=lambda x: x[0], reverse=True)[:10]:
            pi, si = rec['para_idx'], rec['sent_idx']
            source = rec['source']
            pairs = rec.get('qwen_pairs', [])
            _, old_misses = align_greedy(pairs, rec['jieba_segments'])
            _, new_misses = align_spans(rec['source'], pairs, rec['jieba_segments'])
            print(f'  para {pi+1} s{si+1}: +{delta} misses | {source[:60]}')
            print(f'    jieba: {rec["jieba_segments"]}')
            print(f'    qwen : {[p.get("seg") for p in pairs]}')

    # diagnose remaining failures
    print(f'\n=== Diagnose remaining new-algorithm failures ===')
    remaining = []
    for rec in records:
        if not rec.get('qwen_parse_ok', False):
            remaining.append((rec, 'parse_failed'))
            continue
        _, new_misses = align_spans(rec['source'], rec.get('qwen_pairs', []), rec['jieba_segments'])
        if new_misses:
            remaining.append((rec, 'span_miss'))

    fail_types = Counter(t for _, t in remaining)
    print(f'  Parse-failed sentences       : {fail_types["parse_failed"]}')
    print(f'  Span-miss sentences          : {fail_types["span_miss"]}')

    print(f'\n  Sample span-miss sentences:')
    shown = 0
    for rec, t in remaining:
        if t != 'span_miss':
            continue
        if shown >= 5:
            break
        shown += 1
        source = rec['source']
        pairs = rec.get('qwen_pairs', [])
        segs = rec['jieba_segments']
        glosses, _ = align_spans(source, pairs, segs)
        q_tokens = [p.get('seg', '') for p in pairs]
        q_spans = _build_spans(source, q_tokens)
        j_spans = _build_spans(source, segs)
        print(f'\n  para {rec["para_idx"]+1} s{rec["sent_idx"]+1}: {source}')
        print(f'  jieba : {segs}')
        print(f'  qwen  : {q_tokens}')
        miss_segs = [seg for seg, g in zip(segs, glosses) if not g]
        print(f'  missed jieba segs: {miss_segs}')
        bad_q = [tok for tok, sp in zip(q_tokens, q_spans) if sp is None]
        if bad_q:
            print(f'  unfindable qwen tokens: {bad_q}')


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    path = sys.argv[1] if len(sys.argv) > 1 else 'example-data/chapter1-debug.json'
    records = load_debug(path)
    analyse(records)


# ── logbook ───────────────────────────────────────────────────────────────────
# one line per change → resulting new-algorithm fallback rate (chapter 1, 3701 segs)
#
# baseline (greedy)                                      old=5.5%  new=1.5%
# fix sort crash (tuple cmp on dict)                     old=5.5%  new=1.5%  (no score change)
# lenient JSON repair (newline / extra-data parse fails) old=4.2%  new=0.2%
# same-segment fallback + COMMON_GLOSSES table           old=4.2%  new=0.0%
