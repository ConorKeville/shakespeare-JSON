from __future__ import annotations

import json
import unicodedata
from pathlib import Path


PUNCT_CHARS = {
    ',', '.', ';', ':', '?', '!', '-', '—', '–', '’', '‘', '“', '”', '[', ']',
    '(', ')'
}

DASH_KIND = {'-': 'hyphen', '—': 'em', '–': 'en'}


def normalize_word(word: str) -> str:
    ascii_word = unicodedata.normalize('NFKD', word).encode('ascii', 'ignore').decode('ascii')
    return ascii_word.lower() if ascii_word else word.lower()


def build_tokens(text: str, italic: bool, serial: str) -> list[dict]:
    tokens: list[dict] = []
    pre = ''
    idx = 1
    pos = 0
    while pos < len(text):
        if text[pos].isspace():
            pre += text[pos]
            pos += 1
            continue
        chunk = ''
        while pos < len(text) and not text[pos].isspace():
            chunk += text[pos]
            pos += 1
        parts: list[tuple[str, str]] = []
        current = ''
        for ch in chunk:
            if ch in PUNCT_CHARS:
                if current:
                    parts.append(('word', current))
                    current = ''
                parts.append(('punct', ch))
            else:
                current += ch
        if current:
            parts.append(('word', current))
        for part_idx, (kind, value) in enumerate(parts):
            token = {
                'i': idx,
                'type': 'word' if kind == 'word' else 'punct',
                's': value,
                'pre': pre if part_idx == 0 else '',
                'serial': f"{serial}-t{idx:03d}",
            }
            if italic:
                token['em'] = True
            if kind == 'word':
                token['norm'] = normalize_word(value)
            else:
                if value in {'’', '‘'}:
                    norm = "'"
                elif value in {'“', '”'}:
                    norm = '"'
                else:
                    norm = value
                token['norm'] = norm
                punct_info = None
                if value in DASH_KIND:
                    punct_info = {'kind': 'dash', 'dash': DASH_KIND[value], 'quote': None, 'role': None}
                elif value == '.':
                    punct_info = {'kind': 'period', 'dash': None, 'quote': None, 'role': None}
                elif value == ',':
                    punct_info = {'kind': 'comma', 'dash': None, 'quote': None, 'role': None}
                elif value == ';':
                    punct_info = {'kind': 'semicolon', 'dash': None, 'quote': None, 'role': None}
                elif value == ':':
                    punct_info = {'kind': 'colon', 'dash': None, 'quote': None, 'role': None}
                elif value == '?':
                    punct_info = {'kind': 'question', 'dash': None, 'quote': None, 'role': None}
                elif value == '!':
                    punct_info = {'kind': 'exclamation', 'dash': None, 'quote': None, 'role': None}
                elif value == '[':
                    punct_info = {'kind': 'bracket_open', 'dash': None, 'quote': None, 'role': None}
                elif value == ']':
                    punct_info = {'kind': 'bracket_close', 'dash': None, 'quote': None, 'role': None}
                if punct_info:
                    token['punct'] = punct_info
            tokens.append(token)
            idx += 1
        pre = ''
    return tokens


def retokenize(item: dict, text: str, italic: bool, span_type: str) -> None:
    new_span = {
        'type': span_type,
        'em': italic,
        'text': text,
        'tokens': build_tokens(text, italic, item['serial']),
    }
    item['spans'] = [new_span]

def dedupe_span_text(text: str) -> str:
    stripped = text.strip()
    half = len(stripped) // 2
    if stripped[:half].strip() == stripped[half:].strip() and half != 0:
        return stripped[:half].strip()
    if '. ' in stripped:
        first, *rest = stripped.split('. ')
        first_sentence = first.strip() + '.'
        remainder = '. '.join(rest).strip()
        if remainder == first_sentence:
            return first_sentence
    return stripped


def consolidate_speeches(items: list[dict]) -> list[dict]:
    result: list[dict] = []
    last = None
    for item in items:
        if item['kind'] == 'speech':
            if last is not None and last['kind'] == 'speech' and last['speaker'] == item['speaker']:
                last['spans'].extend(item['spans'])
            else:
                result.append(item)
                last = item
        else:
            result.append(item)
            last = None
    return result


def renumber(data: dict) -> None:
    unit_id = data['meta']['unit']['unit_id']
    line_no = data['meta']['numbering']['line_start']
    speech_seq = 1
    for item in data['items']:
        if item['kind'] == 'speech':
            item['speech_seq'] = speech_seq
            item['speech_id'] = f"{unit_id}-sp{speech_seq:04d}"
            item['line_number'] = line_no
            item['line_serial'] = f"{unit_id}-l{line_no:04d}"
            speech_seq += 1
            line_no += len(item['spans'])
        else:
            item['speech_seq'] = None
            item['speech_id'] = None
            if 'line_number' in item:
                item['line_number'] = None
            if 'line_serial' in item:
                item['line_serial'] = None


def drop_heading(items: list[dict], text: str) -> list[dict]:
    return [item for item in items if not (item['kind'] == 'heading' and ' '.join(span['text'] for span in item['spans']) == text)]


def fix_alencon(items: list[dict]) -> list[dict]:
    result: list[dict] = []
    pending_source = None
    for item in items:
        if item['kind'] == 'speech':
            full_text = ' '.join(span['text'] for span in item['spans']).strip()
            if full_text == 'ALENÇON.':
                pending_source = item['speaker']
                continue
            if pending_source is not None and item['speaker'] == pending_source:
                item['speaker'] = 'ALENÇON'
            else:
                pending_source = None
        else:
            pending_source = None
        result.append(item)
    return result


def fix_scene1(data: dict) -> None:
    items = consolidate_speeches(data['items'])
    for item in items:
        if item['kind'] == 'speech':
            for span in item['spans']:
                if 'Guysors' in span['text']:
                    span['text'] = span['text'].replace('Guysors', 'Gisors')
                    for tok in span['tokens']:
                        if tok['s'] == 'Guysors':
                            tok['s'] = 'Gisors'
                            tok['norm'] = 'gisors'
    data['items'] = items
    renumber(data)


def fix_scene2(data: dict) -> None:
    items = drop_heading(data['items'], 'The First Part of Henry the Sixth')
    for idx, item in enumerate(items):
        text = ' '.join(span['text'] for span in item['spans']) if item['spans'] else ''
        if item['kind'] == 'stage' and 'Sound a Flourish' in text:
            new_text = 'Sound a flourish. Enter Charles, Alençon, and Reignier, marching with drum and soldiers.'
            retokenize(item, new_text, True, 'stage')
            if idx + 1 < len(items) and items[idx + 1]['kind'] == 'stage':
                del items[idx + 1]
            break
    idx = 0
    while idx < len(items):
        item = items[idx]
        if item['kind'] == 'speech' and item['speaker'] == 'CHARLES':
            text = ' '.join(span['text'] for span in item['spans'])
            if text.startswith('Here alarum;'):
                next_text = ''
                if idx + 1 < len(items):
                    next_item = items[idx + 1]
                    next_text = ' '.join(span['text'] for span in next_item['spans']) if next_item['kind'] == 'speech' else ''
                combined = 'Alarum. The French are beaten back by the English with great loss. Re-enter Charles, Alençon, and Reignier.'
                item['kind'] = 'stage'
                item['speaker'] = None
                item['line_number'] = None
                item['line_serial'] = None
                item['speech_seq'] = None
                item['speech_id'] = None
                retokenize(item, combined, True, 'stage')
                if next_text.startswith('Re-enter'):
                    del items[idx + 1]
                break
        idx += 1
    items = fix_alencon(items)
    for item in items:
        if item['kind'] == 'speech':
            text = ' '.join(span['text'] for span in item['spans'])
            if text.startswith('Re-enter the Bastard of Orleans'):
                item['kind'] = 'stage'
                item['speaker'] = None
                retokenize(item, 'Re-enter the Bastard of Orleans, with Joan la Pucelle.', True, 'stage')
            elif text.startswith('Sound, sound alarum!'):
                # ensure retained as speech; nothing to do
                pass
    items = consolidate_speeches(items)
    for item in items:
        if item['kind'] == 'speech' and '(within)' in item['speaker']:
            combined = ' '.join(span['text'].strip() for span in item['spans'] if span['text'].strip())
            retokenize(item, dedupe_span_text(combined), False, 'speech')
    data['items'] = items
    renumber(data)


def fix_scene3(data: dict) -> None:
    items = []
    original_items = drop_heading(data['items'], 'The First Part of Henry the Sixth')
    skip_next = False
    for idx, item in enumerate(original_items):
        if skip_next:
            skip_next = False
            continue
        if item['kind'] == 'speech' and item['speaker'] == 'GLOUCESTER':
            text = ' '.join(span['text'] for span in item['spans'])
            if text.startswith('[_Gloucester’s men rush'):
                item['kind'] = 'stage'
                item['speaker'] = None
                item['line_number'] = None
                item['line_serial'] = None
                item['speech_seq'] = None
                item['speech_id'] = None
                stage_text = 'Gloucester’s men rush at the Tower gates. Woodville, the Lieutenant, speaks within.'
                retokenize(item, stage_text, True, 'stage')
            elif text.startswith('Here Gloucester’s men beat out'):
                if idx + 1 < len(original_items) and original_items[idx + 1]['kind'] == 'speech' and original_items[idx + 1]['speaker'] == 'GLOUCESTER':
                    skip_next = True
                item['kind'] = 'stage'
                item['speaker'] = None
                item['line_number'] = None
                item['line_serial'] = None
                item['speech_seq'] = None
                item['speech_id'] = None
                stage_text = 'Here Gloucester’s men beat out the Cardinal’s men, and enter in the hurly-burly the Mayor of London and his Officers.'
                retokenize(item, stage_text, True, 'stage')
        if item['kind'] == 'stage' and 'Enter to the Protector' in ' '.join(span['text'] for span in item['spans']):
            stage_text = 'Enter Winchester and his men in tawny coats to the Protector at the Tower gates.'
            retokenize(item, stage_text, True, 'stage')
            if idx + 1 < len(original_items) and original_items[idx + 1]['kind'] == 'speech' and original_items[idx + 1]['speaker'] == 'WINCHESTER':
                skip_next = True
        items.append(item)
    for item in items:
        if item['kind'] == 'speech' and item['speaker'] in {'FIRST WARDER', 'SECOND WARDER', 'WOODVILLE'}:
            text = ' '.join(span['text'] for span in item['spans'])
            if text.strip().startswith('Within.'):
                cleaned = text.strip()[len('Within.'):].strip()
                if item['speaker'] == 'FIRST WARDER':
                    item['speaker'] = 'FIRST WARDER (within)'
                elif item['speaker'] == 'SECOND WARDER':
                    item['speaker'] = 'SECOND WARDER (within)'
                else:
                    item['speaker'] = 'WOODVILLE (within)'
                retokenize(item, cleaned, False, 'speech')
    items = consolidate_speeches(items)
    data['items'] = items
    renumber(data)


def fix_scene4(data: dict) -> None:
    items = drop_heading(data['items'], 'The First Part of Henry the Sixth')
    cleaned: list[dict] = []
    skip_next = False
    for idx, item in enumerate(items):
        if skip_next:
            skip_next = False
            continue
        if item['kind'] == 'speech' and item['speaker'] == 'SALISBURY':
            text = ' '.join(span['text'] for span in item['spans'])
            if text.startswith('Enter, on the turrets'):
                next_text = ''
                if idx + 1 < len(items) and items[idx + 1]['kind'] == 'speech' and items[idx + 1]['speaker'] == 'SALISBURY':
                    next_text = ' '.join(span['text'] for span in items[idx + 1]['spans'])
                    skip_next = True
                stage_text = 'Enter, on the turrets, Salisbury and Talbot, Sir William Glansdale, Sir Thomas Gargrave, and others.'
                item['kind'] = 'stage'
                item['speaker'] = None
                item['line_number'] = None
                item['line_serial'] = None
                item['speech_seq'] = None
                item['speech_id'] = None
                retokenize(item, stage_text, True, 'stage')
        cleaned.append(item)
    cleaned = consolidate_speeches(cleaned)
    data['items'] = cleaned
    renumber(data)


def fix_scene5(data: dict) -> None:
    items = drop_heading(data['items'], 'The First Part of Henry the Sixth')
    new_items: list[dict] = []
    idx = 0
    while idx < len(items):
        item = items[idx]
        if item['kind'] == 'heading' and 'Here an alarum again' in ' '.join(span['text'] for span in item['spans']):
            combined = 'Here an alarum again, and Talbot pursueth the Dauphin and driveth him; then enter Joan la Pucelle, driving Englishmen before her, and exit after them. Then re-enter Talbot.'
            stage_item = {
                'seq': item['seq'],
                'serial': item['serial'],
                'kind': 'stage',
                'subtype': None,
                'speaker': None,
                'speech_id': None,
                'speech_seq': None,
                'line_number': None,
                'line_serial': None,
                'subsection': None,
                'spans': item['spans'],
            }
            retokenize(stage_item, combined, True, 'stage')
            new_items.append(stage_item)
            idx += 3
            continue
        new_items.append(item)
        idx += 1
    new_items = consolidate_speeches(new_items)
    data['items'] = new_items
    renumber(data)


def fix_scene6(data: dict) -> None:
    items = drop_heading(data['items'], 'The First Part of Henry the Sixth')
    for idx, item in enumerate(items):
        if item['kind'] == 'heading' and 'Flourish. Enter on the walls' in ' '.join(span['text'] for span in item['spans']):
            combined = 'Flourish. Enter on the walls Joan la Pucelle, Charles, Reignier, Alençon, and Soldiers.'
            stage_item = {
                'seq': item['seq'],
                'serial': item['serial'],
                'kind': 'stage',
                'subtype': None,
                'speaker': None,
                'speech_id': None,
                'speech_seq': None,
                'line_number': None,
                'line_serial': None,
                'subsection': None,
                'spans': item['spans'],
            }
            retokenize(stage_item, combined, True, 'stage')
            items[idx] = stage_item
            if idx + 1 < len(items) and items[idx + 1]['kind'] == 'heading':
                del items[idx + 1]
            break
    items = fix_alencon(items)
    items = consolidate_speeches(items)
    data['items'] = items
    renumber(data)


def main() -> None:
    base = Path('henry-vi-part1/01_acts/Act_01')
    scenes = {
        'A01_S01_Westminster_Abbey.json': fix_scene1,
        'A01_S02_France_Before_Orleans.json': fix_scene2,
        'A01_S03_London_Before_the_Tower.json': fix_scene3,
        'A01_S04_Orleans.json': fix_scene4,
        'A01_S05_Before_Orleans.json': fix_scene5,
        'A01_S06_Orleans.json': fix_scene6,
    }
    for filename, fixer in scenes.items():
        path = base / filename
        with path.open('r', encoding='utf-8') as f:
            data = json.load(f)
        fixer(data)
        with path.open('w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write('\n')


if __name__ == '__main__':
    main()
