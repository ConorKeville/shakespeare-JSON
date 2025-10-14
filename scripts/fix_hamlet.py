import json
import re
from copy import deepcopy


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def renumber_seq(items):
    for idx, item in enumerate(items, start=1):
        item["seq"] = idx


def next_serial_factory(items, prefix):
    pattern = re.compile(rf"{re.escape(prefix)}i(\d+)")
    max_val = 0
    for item in items:
        m = pattern.search(item.get("serial", ""))
        if m:
            max_val = max(max_val, int(m.group(1)))
    counter = max_val

    def next_serial():
        nonlocal counter
        counter += 1
        return f"{prefix}i{counter:04d}"

    return next_serial


def retokenize(tokens):
    for idx, token in enumerate(tokens, start=1):
        token["i"] = idx


def tokens_to_text(tokens):
    parts = []
    for tok in tokens:
        parts.append(tok.get("pre", ""))
        parts.append(tok["s"])
    return "".join(parts)


def extract_stage_spans(items, idx, subtype, serial_gen, position="before"):
    item = items[idx]
    stage_spans = [span for span in item.get("spans", []) if span["type"] == "stage"]
    if not stage_spans:
        return idx

    stage_items = []
    for span in stage_spans:
        tokens = []
        for orig_tok in span.get("tokens", []):
            tok = deepcopy(orig_tok)
            tok.pop("em", None)
            if tok["type"] == "word":
                tok["norm"] = tok["s"].lower()
            tokens.append(tok)
        if tokens:
            tokens[0]["pre"] = ""
            for tok in tokens[1:]:
                if tok["type"] == "word" and tok.get("pre", "") == "":
                    tok["pre"] = " "
                if tok["type"] == "punct":
                    tok["pre"] = ""
        retokenize(tokens)
        stage_item = {
            "seq": None,
            "serial": serial_gen(),
            "kind": "stage",
            "subtype": subtype,
            "speaker": None,
            "speech_id": None,
            "speech_seq": None,
            "line_number": None,
            "line_serial": None,
            "subsection": None,
            "spans": [
                {
                    "type": "stage",
                    "em": True,
                    "text": tokens_to_text(tokens),
                    "stage": None,
                    "tokens": tokens,
                }
            ],
        }
        stage_items.append(stage_item)

    speech_tokens = []
    for span in item.get("spans", []):
        if span["type"] != "speech":
            continue
        for tok in span.get("tokens", []):
            new_tok = deepcopy(tok)
            new_tok.pop("em", None)
            speech_tokens.append(new_tok)

    if speech_tokens:
        speech_tokens[0]["pre"] = ""
        retokenize(speech_tokens)
        item["spans"] = [
            {
                "type": "speech",
                "em": False,
                "text": tokens_to_text(speech_tokens),
                "tokens": speech_tokens,
            }
        ]
    else:
        item["spans"] = []

    if position == "before":
        for stage_item in stage_items:
            items.insert(idx, stage_item)
            idx += 1
        speech_idx = idx
    elif position == "after":
        speech_idx = idx
        insert_pos = idx + 1
        for stage_item in stage_items:
            items.insert(insert_pos, stage_item)
            insert_pos += 1
    else:
        speech_idx = idx

    return speech_idx


def merge_into_previous_line(items, stage_idx):
    stage_item = items.pop(stage_idx)
    text_span = stage_item["spans"][0]
    tokens = [deepcopy(t) for t in text_span["tokens"]]
    speech_item = items[stage_idx - 1]
    span = speech_item["spans"][0]
    span["text"] = span["text"].rstrip(" ,") + " " + text_span["text"].strip()
    speech_tokens = span["tokens"]
    if speech_tokens:
        speech_tokens[-1]["pre"] = speech_tokens[-1].get("pre", "")
    if tokens:
        tokens[0]["pre"] = " "
    for tok in tokens:
        tok.pop("em", None)
    speech_tokens.extend(tokens)
    for tok in speech_tokens:
        if tok["type"] == "word":
            tok["norm"] = tok["s"].lower()
    retokenize(speech_tokens)


def set_speaker_for_lines(data, speech_id, seqs, speaker):
    for item in data["items"]:
        if item.get("speech_id") == speech_id and item.get("speech_seq") in seqs:
            item["speaker"] = speaker


def act1_scene5(path):
    data = load(path)
    items = data["items"]

    # Merge "Within the book ..." into the previous HAMLET line.
    for idx, item in enumerate(items):
        if item.get("kind") == "stage" and any(
            span["text"].startswith("Within the book and volume of my brain")
            for span in item.get("spans", [])
        ):
            merge_into_previous_line(items, idx)
            break

    # Fix misattributed lines 114-116.
    set_speaker_for_lines(data, "hamlet-a01-s05-s0021", {1, 2, 3}, "HAMLET")
    for idx, item in enumerate(items):
        if (
            item.get("kind") == "speech"
            and item.get("speech_id") == "hamlet-a01-s05-s0021"
            and item.get("speech_seq") == 1
        ):
            # Update preceding speaker label to HAMLET.
            label_idx = idx - 1
            while label_idx >= 0 and items[label_idx]["kind"] != "speaker_label":
                label_idx -= 1
            if label_idx >= 0:
                items[label_idx]["speaker"] = "HAMLET"
            break

    # Create new speaker label for HORATIO and MARCELLUS after Hamlet's lines.
    insert_idx = None
    for idx, item in enumerate(items):
        if (
            item.get("kind") == "speech"
            and item.get("speech_id") == "hamlet-a01-s05-s0021"
            and item.get("speech_seq") == 3
        ):
            insert_idx = idx + 1
            break
    if insert_idx is not None:
        next_serial = next_serial_factory(items, "hamlet-a01-s05-")
        label_item = {
            "seq": None,
            "serial": next_serial(),
            "kind": "speaker_label",
            "subtype": None,
            "speaker": "HORATIO and MARCELLUS",
            "speech_id": None,
            "speech_seq": None,
            "line_number": None,
            "line_serial": None,
            "subsection": None,
            "spans": [],
        }
        items.insert(insert_idx, label_item)

    # Reassign the subsequent speech items to HORATIO and MARCELLUS and clean stage cues.
    new_speech_id = "hamlet-a01-s05-s0020"
    seq = 1
    idx = 0
    while idx < len(items):
        item = items[idx]
        if item.get("kind") == "speech" and item.get("line_number") in {117, 118, 119}:
            item["speaker"] = "HORATIO and MARCELLUS"
            item["speech_id"] = new_speech_id
            item["speech_seq"] = seq
            seq += 1

            # Handle stage text inside the speech.
            stage_spans = []
            remaining_spans = []
            for span in item.get("spans", []):
                if span["type"] == "stage":
                    stage_spans.append(span)
                else:
                    remaining_spans.append(span)
            embedded_stage = None
            for span in remaining_spans:
                if span["type"] == "speech":
                    tokens = span["tokens"]
                    if tokens and tokens[0].get("s") == "[":
                        end_idx = None
                        for t_idx, tok in enumerate(tokens):
                            if tok.get("s") == "]":
                                end_idx = t_idx
                                break
                        if end_idx is not None:
                            stage_tokens = [deepcopy(tok) for tok in tokens[: end_idx + 1]]
                            del tokens[: end_idx + 1]
                            if tokens:
                                tokens[0]["pre"] = ""
                            word_tokens = [
                                tok
                                for tok in stage_tokens
                                if tok["type"] == "word"
                                or (tok["type"] == "punct" and tok["s"] in {".", "!", "?", "—", "-"})
                            ]
                            for tok in word_tokens:
                                tok.pop("em", None)
                                tok["pre"] = tok.get("pre", "").strip()
                                if tok["type"] == "word":
                                    tok["norm"] = tok["s"].lower()
                            if word_tokens:
                                word_tokens[0]["pre"] = ""
                            retokenize(tokens)
                            embedded_stage = {
                                "text": tokens_to_text(word_tokens),
                                "tokens": word_tokens,
                            }
                            break
            if stage_spans:
                next_serial = next_serial_factory(items, "hamlet-a01-s05-")
                for span in stage_spans:
                    tokens = [deepcopy(t) for t in span["tokens"] if t["type"] != "punct" or t["s"] != "_"]
                    for tok in tokens:
                        tok.pop("em", None)
                        tok["pre"] = tok.get("pre", "").strip()
                        if tok["type"] == "word":
                            tok["norm"] = tok["s"].lower()
                    if tokens:
                        tokens[0]["pre"] = ""
                    retokenize(tokens)
                    stage_text = tokens_to_text(tokens)
                    stage_item = {
                        "seq": None,
                        "serial": next_serial(),
                        "kind": "stage",
                        "subtype": "within",
                        "speaker": None,
                        "speech_id": None,
                        "speech_seq": None,
                        "line_number": None,
                        "line_serial": None,
                        "subsection": None,
                        "spans": [
                            {
                                "type": "stage",
                                "em": True,
                                "text": stage_text.strip(),
                                "stage": None,
                                "tokens": tokens,
                            }
                        ],
                    }
                    items.insert(idx, stage_item)
                    idx += 1
            if embedded_stage:
                next_serial = next_serial_factory(items, "hamlet-a01-s05-")
                retokenize(embedded_stage["tokens"])
                stage_item = {
                    "seq": None,
                    "serial": next_serial(),
                    "kind": "stage",
                    "subtype": "within",
                    "speaker": None,
                    "speech_id": None,
                    "speech_seq": None,
                    "line_number": None,
                    "line_serial": None,
                    "subsection": None,
                    "spans": [
                        {
                            "type": "stage",
                            "em": True,
                            "text": embedded_stage["text"],
                            "stage": None,
                            "tokens": embedded_stage["tokens"],
                        }
                    ],
                }
                items.insert(idx, stage_item)
                idx += 1
            item["spans"] = remaining_spans
            for span in item["spans"]:
                if span["type"] == "speech":
                    span["text"] = span["text"].lstrip()
                    for token in span["tokens"]:
                        token.pop("em", None)
                    if span["tokens"]:
                        span["tokens"][0]["pre"] = ""
                    retokenize(span["tokens"])
                    span["text"] = tokens_to_text(span["tokens"])
            idx += 1
        else:
            idx += 1

    # Modernize punctuation: "Yes faith, heartily." -> "Yes, faith, heartily."
    for item in items:
        if item.get("kind") != "speech":
            continue
        for span in item.get("spans", []):
            if span.get("text") == "Yes faith, heartily.":
                tokens = span.get("tokens", [])
                comma_token = {
                    "i": 0,
                    "type": "punct",
                    "s": ",",
                    "norm": ",",
                    "pre": "",
                    "serial": "hamlet-a01-s05-l0143-t006",
                    "punct": {"kind": "comma", "dash": None, "quote": None, "role": None},
                }
                tokens.insert(1, comma_token)
                retokenize(tokens)
                span["text"] = tokens_to_text(tokens)

    renumber_seq(items)
    save(path, data)


def act2_scene2(path):
    data = load(path)
    items = data["items"]
    serial_gen = next_serial_factory(items, "hamlet-a02-s02-")

    idx = 0
    while idx < len(items):
        item = items[idx]
        if item.get("kind") == "speech":
            stage_texts = [span["text"].strip() for span in item.get("spans", []) if span["type"] == "stage"]
            if any(text.startswith("Aside") for text in stage_texts):
                idx = extract_stage_spans(items, idx, "aside", serial_gen)
                idx += 1
                continue
            if any(text.startswith("To ") for text in stage_texts):
                idx = extract_stage_spans(items, idx, "address", serial_gen)
                idx += 1
                continue
        idx += 1

    for item in items:
        if item.get("kind") == "stage" and item.get("subtype") in {"aside", "address"}:
            for span in item.get("spans", []):
                tokens = span.get("tokens", [])
                if not tokens:
                    continue
                tokens[0]["pre"] = ""
                for tok in tokens[1:]:
                    if tok["type"] == "word" and tok.get("pre", "") == "":
                        tok["pre"] = " "
                    if tok["type"] == "punct":
                        tok["pre"] = ""
                retokenize(tokens)
                span["text"] = tokens_to_text(tokens)

    renumber_seq(items)
    save(path, data)


def act3_scene2(path):
    data = load(path)
    items = data["items"]
    serial_gen = next_serial_factory(items, "hamlet-a03-scene-2-a-hall-in-the-castle-")

    idx = 0
    while idx < len(items):
        item = items[idx]
        if item.get("kind") == "speech":
            stage_texts = [span["text"].strip() for span in item.get("spans", []) if span["type"] == "stage"]
            if any(text.startswith("To ") for text in stage_texts):
                idx = extract_stage_spans(items, idx, "address", serial_gen)
                idx += 1
                continue
        idx += 1

    # Normalize italicized "The Mousetrap" title.
    for item in items:
        if item.get("kind") != "speech":
            continue
        new_spans = []
        modified = False
        for span in item.get("spans", []):
            if "_The Mousetrap._" in span.get("text", ""):
                tokens = span.get("tokens", [])
                italic_tokens = []
                remaining_tokens = []
                in_italic = False
                for tok in tokens:
                    if tok["s"] == "_":
                        if not in_italic:
                            in_italic = True
                            continue
                        else:
                            in_italic = False
                            continue
                    copied = deepcopy(tok)
                    copied.pop("em", None)
                    if copied["type"] == "word":
                        copied["norm"] = copied["s"].lower()
                    if in_italic:
                        italic_tokens.append(copied)
                    else:
                        remaining_tokens.append(copied)
                if italic_tokens:
                    italic_tokens[0]["pre"] = ""
                    for tok in italic_tokens[1:]:
                        if tok["type"] == "word" and tok.get("pre", "") == "":
                            tok["pre"] = " "
                        if tok["type"] == "punct":
                            tok["pre"] = ""
                    retokenize(italic_tokens)
                    italic_span = {
                        "type": "speech",
                        "em": False,
                        "style": "italic",
                        "text": tokens_to_text(italic_tokens),
                        "tokens": italic_tokens,
                    }
                    new_spans.append(italic_span)
                    modified = True
                if remaining_tokens:
                    if modified:
                        # Ensure spacing after italic section.
                        if remaining_tokens[0].get("pre", "") == "":
                            remaining_tokens[0]["pre"] = " "
                    retokenize(remaining_tokens)
                    remaining_span = {
                        "type": "speech",
                        "em": False,
                        "text": tokens_to_text(remaining_tokens),
                        "tokens": remaining_tokens,
                    }
                    new_spans.append(remaining_span)
                else:
                    new_spans.append(span)
                continue
            new_spans.append(span)
        if modified:
            item["spans"] = new_spans

    # Fix OCR misread "A whole one, I." -> "A whole one, ay."
    for item in items:
        if item.get("kind") != "speech":
            continue
        for span in item.get("spans", []):
            if span.get("text") == "A whole one, I.":
                for tok in span.get("tokens", []):
                    if tok["type"] == "word" and tok["s"] == "I":
                        tok["s"] = "ay"
                        tok["norm"] = "ay"
                span["text"] = tokens_to_text(span.get("tokens", []))

    for item in items:
        if item.get("kind") == "stage" and item.get("subtype") == "address":
            for span in item.get("spans", []):
                tokens = span.get("tokens", [])
                if not tokens:
                    continue
                tokens[0]["pre"] = ""
                for tok in tokens[1:]:
                    if tok["type"] == "word" and tok.get("pre", "") == "":
                        tok["pre"] = " "
                    if tok["type"] == "punct":
                        tok["pre"] = ""
                retokenize(tokens)
                span["text"] = tokens_to_text(tokens)

    renumber_seq(items)
    save(path, data)


def act3_scene4(path):
    data = load(path)
    items = data["items"]
    serial_gen = next_serial_factory(items, "hamlet-a03-s04-")

    idx = 0
    while idx < len(items):
        item = items[idx]
        if item.get("kind") == "speech":
            stage_texts = [span["text"].strip() for span in item.get("spans", []) if span["type"] == "stage"]
            if any(text.startswith("Within") for text in stage_texts):
                idx = extract_stage_spans(items, idx, "within", serial_gen, position="before")
                idx += 1
                continue
            if any(text.startswith("Behind") for text in stage_texts):
                idx = extract_stage_spans(items, idx, "behind", serial_gen, position="before")
                idx += 1
                continue
            if any(text.startswith("Draws") for text in stage_texts):
                idx = extract_stage_spans(items, idx, "action", serial_gen, position="after")
                idx += 1
                continue
            if any(text.startswith("To ") for text in stage_texts):
                idx = extract_stage_spans(items, idx, "address", serial_gen, position="before")
                idx += 1
                continue
        idx += 1

    for item in items:
        if item.get("kind") == "stage" and item.get("subtype") in {"within", "behind", "address", "action"}:
            for span in item.get("spans", []):
                tokens = span.get("tokens", [])
                if not tokens:
                    continue
                tokens[0]["pre"] = ""
                for tok in tokens[1:]:
                    if tok["type"] == "word" and tok.get("pre", "") == "":
                        tok["pre"] = " "
                    if tok["type"] == "punct":
                        tok["pre"] = ""
                retokenize(tokens)
                span["text"] = tokens_to_text(tokens)

    renumber_seq(items)
    save(path, data)


def act4_scene2(path):
    data = load(path)
    items = data["items"]
    serial_gen = next_serial_factory(items, "hamlet-a04-s02-")

    idx = 0
    while idx < len(items):
        item = items[idx]
        if item.get("kind") == "speech":
            stage_texts = [span["text"].strip() for span in item.get("spans", []) if span["type"] == "stage"]
            if any(text.startswith("Within") for text in stage_texts):
                idx = extract_stage_spans(items, idx, "within", serial_gen, position="before")
                idx += 1
                continue
        idx += 1

    for item in items:
        if item.get("kind") == "stage" and item.get("subtype") == "within":
            for span in item.get("spans", []):
                tokens = span.get("tokens", [])
                if not tokens:
                    continue
                tokens[0]["pre"] = ""
                for tok in tokens[1:]:
                    if tok["type"] == "word" and tok.get("pre", "") == "":
                        tok["pre"] = " "
                    if tok["type"] == "punct":
                        tok["pre"] = ""
                retokenize(tokens)
                span["text"] = tokens_to_text(tokens)

    renumber_seq(items)
    save(path, data)


def act4_scene3(path):
    data = load(path)
    items = data["items"]

    for idx, item in enumerate(items):
        if item.get("kind") == "stage":
            for span in item.get("spans", []):
                if "stairs into the" in span.get("text", ""):
                    if idx == 0:
                        break
                    prev_item = items[idx - 1]
                    if prev_item.get("kind") != "speech":
                        break
                    prev_span = prev_item.get("spans", [])[0]
                    prev_tokens = prev_span.get("tokens", [])
                    new_tokens = []
                    for tok in span.get("tokens", []):
                        copied = deepcopy(tok)
                        copied.pop("em", None)
                        if copied["type"] == "word":
                            copied["norm"] = copied["s"].lower()
                        new_tokens.append(copied)
                    if new_tokens:
                        new_tokens[0]["pre"] = " "
                        for tok in new_tokens[1:]:
                            tok["pre"] = tok.get("pre", "")
                    prev_tokens.extend(new_tokens)
                    retokenize(prev_tokens)
                    prev_span["text"] = tokens_to_text(prev_tokens)
                    items.pop(idx)
                    break

    for idx, item in enumerate(items):
        if item.get("kind") == "speech":
            spans = item.get("spans", [])
            if len(spans) == 1 and spans[0].get("text") == "lobby.":
                if idx == 0:
                    break
                prev_item = items[idx - 1]
                if prev_item.get("kind") != "speech":
                    break
                prev_span = prev_item.get("spans", [])[0]
                prev_tokens = prev_span.get("tokens", [])
                new_tokens = [deepcopy(tok) for tok in spans[0].get("tokens", [])]
                if new_tokens:
                    new_tokens[0]["pre"] = " "
                    for tok in new_tokens[1:]:
                        tok["pre"] = tok.get("pre", "")
                prev_tokens.extend(new_tokens)
                retokenize(prev_tokens)
                prev_span["text"] = tokens_to_text(prev_tokens)
                items.pop(idx)
                break

    renumber_seq(items)
    save(path, data)


if __name__ == "__main__":
    act1_scene5("shakespeare-JSON/hamlet/01_acts/Act_01/A01_S05_A_more_remote_part_of_the_Castle.json")
    act2_scene2("shakespeare-JSON/hamlet/01_acts/Act_02/A02_S02_A_room_in_the_Castle.json")
    act3_scene2("shakespeare-JSON/hamlet/01_acts/Act_03/A03_S02_A_hall_in_the_Castle.json")
    act3_scene4("shakespeare-JSON/hamlet/01_acts/Act_03/A03_S04_Another_room_in_the_Castle.json")
    act4_scene2("shakespeare-JSON/hamlet/01_acts/Act_04/A04_S02_Another_room_in_the_Castle.json")
    act4_scene3("shakespeare-JSON/hamlet/01_acts/Act_04/A04_S03_Another_room_in_the_Castle.json")
