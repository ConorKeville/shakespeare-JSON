import json
import copy
from collections import defaultdict
from pathlib import Path

TARGET_FILES = [
    Path('henry-vi-part1/01_acts/Act_01/A01_S01_Westminster_Abbey.json'),
    Path('henry-vi-part1/01_acts/Act_01/A01_S02_France_Before_Orleans.json'),
    Path('henry-vi-part1/01_acts/Act_01/A01_S03_London_Before_the_Tower.json'),
    Path('henry-vi-part1/01_acts/Act_01/A01_S04_Orleans.json'),
    Path('henry-vi-part1/01_acts/Act_01/A01_S05_Before_Orleans.json'),
    Path('henry-vi-part1/01_acts/Act_01/A01_S06_Orleans.json'),
]

def format_serial(unit_id: str, index: int) -> str:
    return f"{unit_id}-i{index:04d}"

def format_token_serial(item_serial: str, index: int) -> str:
    return f"{item_serial}-t{index:03d}"

def format_line_serial(unit_id: str, line_number: int) -> str:
    return f"{unit_id}-l{line_number:04d}"

def normalize_tokens(span, item_serial):
    tokens = span.get('tokens') or []
    for idx, token in enumerate(tokens, start=1):
        token['i'] = idx
        token['serial'] = format_token_serial(item_serial, idx)
    return span

def process_file(path: Path) -> None:
    data = json.loads(path.read_text(encoding='utf-8'))
    unit_id = data['meta']['unit']['unit_id']
    seq_counter = data['meta'].get('numbering', {}).get('seq_start', 1)
    line_counter = data['meta'].get('numbering', {}).get('line_start', 1)

    new_items = []
    speech_seq_counts = defaultdict(int)

    for item in data['items']:
        kind = item['kind']
        if kind != 'speech':
            new_item = copy.deepcopy(item)
            new_item['seq'] = seq_counter
            item_serial = format_serial(unit_id, seq_counter)
            new_item['serial'] = item_serial
            for span in new_item.get('spans', []):
                normalize_tokens(span, item_serial)
            new_items.append(new_item)
            seq_counter += 1
            continue

        spans = item.get('spans') or []
        speech_id = item.get('speech_id')
        if speech_id is not None and speech_id not in speech_seq_counts:
            speech_seq_counts[speech_id] = 0

        if not spans:
            new_item = copy.deepcopy(item)
            new_item['seq'] = seq_counter
            item_serial = format_serial(unit_id, seq_counter)
            new_item['serial'] = item_serial
            if speech_id is not None:
                speech_seq_counts[speech_id] += 1
                new_item['speech_seq'] = speech_seq_counts[speech_id]
            new_item['line_number'] = line_counter
            new_item['line_serial'] = format_line_serial(unit_id, line_counter)
            for span in new_item.get('spans', []):
                normalize_tokens(span, item_serial)
            new_items.append(new_item)
            seq_counter += 1
            line_counter += 1
            continue

        for span in spans:
            new_item = copy.deepcopy(item)
            new_item['spans'] = [copy.deepcopy(span)]
            new_item['seq'] = seq_counter
            item_serial = format_serial(unit_id, seq_counter)
            new_item['serial'] = item_serial
            if speech_id is not None:
                speech_seq_counts[speech_id] += 1
                new_item['speech_seq'] = speech_seq_counts[speech_id]
            new_item['line_number'] = line_counter
            new_item['line_serial'] = format_line_serial(unit_id, line_counter)
            normalize_tokens(new_item['spans'][0], item_serial)
            new_items.append(new_item)
            seq_counter += 1
            line_counter += 1

    data['items'] = new_items
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

if __name__ == '__main__':
    for file_path in TARGET_FILES:
        process_file(file_path)
