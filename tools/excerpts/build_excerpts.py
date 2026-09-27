import argparse
import bisect
import collections
import io
import json
import math
import os
import sys
import tempfile
import warnings

warnings.filterwarnings("ignore")

import mido
import music21 as m21
from music21.musicxml.m21ToXml import GeneralObjectExporter

sys.path.insert(0, os.path.dirname(__file__))
from specs import ASAP, CHOPIN_FE, CPM, EXCERPTS
from xmlslice import slice_xml

_KERN_CACHE = {}
_XML_CACHE = {}


def kern_xml(path):
    if path not in _KERN_CACHE:
        score = m21.converter.parse(path, format="humdrum")
        _KERN_CACHE[path] = GeneralObjectExporter(score).parse()
    return _KERN_CACHE[path]


def raw_xml(path):
    if path not in _XML_CACHE:
        with open(path, "rb") as handle:
            _XML_CACHE[path] = handle.read()
    return _XML_CACHE[path]


def load_midi(path):
    midi = mido.MidiFile(path)
    tpb = midi.ticks_per_beat
    signatures = []
    elapsed = 0
    for message in midi.tracks[0]:
        elapsed += message.time
        if message.type == "time_signature":
            signatures.append((elapsed, message.numerator, message.denominator))
    notes = {}
    for index, track in enumerate(midi.tracks):
        elapsed = 0
        sounding = {}
        for message in track:
            elapsed += message.time
            if message.type == "note_on" and message.velocity > 0:
                sounding[message.note] = (elapsed, message.velocity)
            elif message.type in ("note_off", "note_on") and message.note in sounding:
                start, velocity = sounding.pop(message.note)
                notes.setdefault(index, []).append((start, elapsed - start, message.note, velocity))
    total = max(note[0] for group in notes.values() for note in group)
    bars = []
    cursor = 0
    position = 0
    while cursor <= total:
        while position + 1 < len(signatures) and signatures[position + 1][0] <= cursor:
            position += 1
        _, numerator, denominator = signatures[position]
        bars.append((cursor, numerator, denominator))
        cursor += int(tpb * 4 * numerator / denominator)
    return tpb, bars, notes


def midi_bar_notes(path, first, last):
    tpb, bars, notes = load_midi(path)
    starts = [bar[0] for bar in bars]
    origin = bars[first - 1][0]
    result = []
    for track in sorted(notes):
        for start, length, pitch, velocity in notes[track]:
            bar = bisect.bisect_right(starts, start)
            if first <= bar <= last:
                result.append(((start - origin) / tpb, length / tpb, pitch, velocity, track))
    return result, bars, tpb


def quantize(value, grid=16):
    return round(value * grid) / grid


def spell(midi, spelling):
    pitch = m21.pitch.Pitch(midi=midi)
    if not spelling:
        return pitch
    name = spelling[midi % 12]
    octave = midi // 12 - 1
    if name.startswith("B#"):
        octave -= 1
    if name.startswith("Cb"):
        octave += 1
    return m21.pitch.Pitch(f"{name}{octave}")


def cpm_score(spec):
    path = os.path.join(ROOTS[CPM], spec["source"]["path"])
    first, last = spec["bars"]
    notes, bars, tpb = midi_bar_notes(path, first, last)
    score = m21.stream.Score()
    tracks = sorted({note[4] for note in notes})
    chosen = (tracks[0],) if spec["source"].get("tracks") == "right" or len(tracks) == 1 else (tracks[0], tracks[-1])
    spelling = spec["source"].get("spelling")
    for track in chosen:
        part = m21.stream.Part()
        own = [note for note in notes if note[4] == track]
        mean = sum(note[2] for note in own) / max(len(own), 1)
        for bar in range(first, last + 1):
            start_tick, numerator, denominator = bars[bar - 1]
            bar_start = (start_tick - bars[first - 1][0]) / tpb
            bar_length = 4 * numerator / denominator
            measure = m21.stream.Measure(number=bar)
            if bar == first:
                measure.insert(0, m21.clef.TrebleClef() if track == tracks[0] else (m21.clef.TrebleClef() if mean >= 60 else m21.clef.BassClef()))
                measure.insert(0, m21.key.KeySignature(spec["source"].get("key_sharps", 0)))
                measure.insert(0, m21.meter.TimeSignature(f"{numerator}/{denominator}"))
            onsets = collections.OrderedDict()
            for offset, length, pitch, velocity, _ in sorted(own):
                local = quantize(offset - bar_start)
                if 0 <= local < bar_length:
                    onsets.setdefault(local, []).append(pitch)
            keys = list(onsets)
            for index, local in enumerate(keys):
                following = keys[index + 1] if index + 1 < len(keys) else bar_length
                length = max(quantize(following - local), 0.0625)
                pitches = [spell(pitch, spelling) for pitch in sorted(set(onsets[local]))]
                element = m21.note.Note(pitches[0]) if len(pitches) == 1 else m21.chord.Chord(pitches)
                element.quarterLength = length
                measure.insert(local, element)
            measure.makeRests(fillGaps=True, timeRangeFromBarDuration=True, inPlace=True)
            part.append(measure)
        score.insert(0, part)
    score.makeNotation(inPlace=True)
    return GeneralObjectExporter(score).parse()


def excerpt_xml(spec):
    kind = spec["source"]["kind"]
    first, last = spec["bars"]
    if kind == ASAP:
        data = slice_xml(raw_xml(os.path.join(ROOTS[ASAP], spec["source"]["path"])), first, last)
    elif kind == CHOPIN_FE:
        data = slice_xml(kern_xml(os.path.join(ROOTS[CHOPIN_FE], spec["source"]["path"])), first, last)
    elif kind == CPM:
        data = cpm_score(spec)
    else:
        raise ValueError(kind)
    if spec.get("rolled"):
        data = add_arpeggios(data)
    return data


def add_arpeggios(data):
    from lxml import etree
    root = etree.fromstring(data)
    for measure in root.iter("measure"):
        notes = measure.findall("note")
        for index, note in enumerate(notes):
            in_chord = note.find("chord") is not None or (index + 1 < len(notes) and notes[index + 1].find("chord") is not None)
            if not in_chord or note.find("rest") is not None:
                continue
            notations = note.find("notations")
            if notations is None:
                notations = etree.SubElement(note, "notations")
            if notations.find("arpeggiate") is None:
                etree.SubElement(notations, "arpeggiate")
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8")


def parse_xml_bytes(data):
    with tempfile.NamedTemporaryFile(suffix=".musicxml", delete=False) as handle:
        handle.write(data)
        name = handle.name
    try:
        return m21.converter.parse(name, format="musicxml")
    finally:
        os.unlink(name)


def beat_length(score):
    signature = score.recurse().getElementsByClass("TimeSignature").first()
    if signature and signature.denominator == 8 and signature.numerator % 3 == 0:
        return 1.5
    return 1.0


def events_from_score(score, spec):
    pedal = spec.get("pedal", "none")
    beat = beat_length(score)
    events = []
    for index, part in enumerate(score.parts):
        hand = "R" if index == 0 else "L"
        measures = list(part.getElementsByClass("Measure"))
        if not measures:
            continue
        origin = measures[0].offset
        bar_ends = [measure.offset - origin + measure.barDuration.quarterLength for measure in measures]
        stripped = part.stripTies(inPlace=False)
        hidden_marks = set()
        visible = []
        for element in stripped.recurse().notes:
            if element.duration.isGrace:
                continue
            offset = float(element.getOffsetInHierarchy(stripped)) - origin
            length = float(element.duration.quarterLength)
            pitches = [pitch.midi for pitch in element.pitches]
            if element.style.hideObjectOnPrint:
                for pitch in pitches:
                    hidden_marks.add((round(offset, 3), pitch))
                    events.append([offset, length, pitch, hand, False])
            else:
                rolled = spec.get("rolled", False) or any("Arpeggio" in type(mark).__name__ for mark in element.expressions)
                for order, pitch in enumerate(sorted(pitches)):
                    visible.append([offset, length, pitch, hand, rolled, order])
        for offset, length, pitch, hand_, rolled, order in visible:
            if (round(offset, 3), pitch) in hidden_marks:
                continue
            events.append([offset, length, pitch, hand_, rolled])
    result = []
    for offset, length, pitch, hand, _ in events:
        sound = length
        if pedal == "beat":
            sound = max(length, math.ceil((offset + length) / beat - 1e-6) * beat - offset)
        elif pedal == "bar":
            ends = [end for end in bar_ends_for(score) if end > offset + 1e-6]
            sound = max(length, (ends[0] if ends else offset + length) - offset)
        result.append([round(offset, 4), round(length, 4), pitch, 0, hand, round(sound, 4)])
    result = dedupe(result)
    if spec.get("rolled"):
        groups = collections.defaultdict(list)
        for item in result:
            groups[item[0]].append(item)
        for onset, items in groups.items():
            if len(items) > 1:
                for order, item in enumerate(sorted(items, key=lambda entry: entry[2])):
                    delay = round(order * 0.035, 4)
                    item[0] = round(onset + delay, 4)
                    item[5] = round(max(item[5] - delay, 0.1), 4)
        result.sort(key=lambda item: (item[0], item[2]))
    return result


def dedupe(events):
    best = {}
    for item in events:
        key = (round(item[0], 3), item[2])
        if key not in best or item[5] > best[key][5]:
            best[key] = item
    return sorted(best.values(), key=lambda item: (item[0], item[2]))


def bar_ends_for(score):
    part = score.parts[0]
    measures = list(part.getElementsByClass("Measure"))
    origin = measures[0].offset
    return [measure.offset - origin + measure.barDuration.quarterLength for measure in measures]


def events_from_midi(spec):
    path = os.path.join(ROOTS[CPM], spec["source"]["path"])
    first, last = spec["bars"]
    notes, bars, tpb = midi_bar_notes(path, first, last)
    tracks = sorted({note[4] for note in notes})
    if spec["source"].get("tracks") == "right":
        notes = [note for note in notes if note[4] == tracks[0]]
    result = []
    for offset, length, pitch, velocity, track in notes:
        hand = "R" if track == tracks[0] else "L"
        result.append([round(offset, 4), round(length, 4), pitch, velocity, hand, round(length, 4)])
    if spec.get("pedal") == "bar":
        ends = []
        for bar in range(first, last + 1):
            start_tick, numerator, denominator = bars[bar - 1]
            ends.append((start_tick - bars[first - 1][0]) / tpb + 4 * numerator / denominator)
        for item in result:
            later = [end for end in ends if end > item[0] + 1e-6]
            if later:
                item[5] = round(max(item[1], later[0] - item[0]), 4)
    result.sort(key=lambda item: (item[0], item[2]))
    return result


def pitch_bag(kind, path, first, last):
    if kind == CPM:
        notes, _, _ = midi_bar_notes(os.path.join(ROOTS[CPM], path), first, last)
        return collections.Counter(pitch for _, pitch in {(round(note[0] * 24) / 24, note[2]) for note in notes})
    data = slice_xml(raw_xml(os.path.join(ROOTS[kind], path)) if kind == ASAP else kern_xml(os.path.join(ROOTS[kind], path)), first, last)
    score = parse_xml_bytes(data)
    seen = set()
    for part in score.parts:
        stripped = part.stripTies(inPlace=False)
        for element in stripped.recurse().notes:
            if element.duration.isGrace or element.style.hideObjectOnPrint:
                continue
            offset = round(float(element.getOffsetInHierarchy(stripped)), 3)
            for pitch in element.pitches:
                seen.add((offset, pitch.midi))
    return collections.Counter(pitch for _, pitch in seen)


def similarity(a, b):
    union = sum((a | b).values())
    return sum((a & b).values()) / union if union else 0.0


def verify(spec, primary_bag):
    reports = []
    first, last = spec["bars"]
    for other in spec.get("verify", []):
        best = (0.0, 0)
        for shift in range(-4, 5):
            try:
                bag = pitch_bag(other["kind"], other["path"], first + shift, last + shift)
            except Exception:
                continue
            score = similarity(primary_bag, bag)
            if score > best[0]:
                best = (score, shift)
        reports.append({"source": other["kind"], "match": round(best[0], 3), "bar_shift": best[1]})
    return reports


SOURCE_LABELS = {
    ASAP: {"name": "ASAP dataset (Foscarin et al.)", "license": "CC BY-NC-SA 4.0", "url": "https://github.com/fosfrancesco/asap-dataset"},
    CHOPIN_FE: {"name": "First Editions of Fryderyk Chopin's Music, Fryderyk Chopin Institute", "license": "CC BY 4.0", "url": "https://chopinscores.org"},
    CPM: {"name": "Classical Piano MIDI, Bernd Krueger (via ACPAS)", "license": "CC BY-SA 3.0 DE", "url": "http://www.piano-midi.de"},
}


def build(out_dir):
    os.makedirs(out_dir, exist_ok=True)
    index = {"version": 1, "techniques": collections.OrderedDict(), "excerpts": {}, "sources": SOURCE_LABELS}
    for spec in EXCERPTS:
        data = excerpt_xml(spec)
        with open(os.path.join(out_dir, f"{spec['id']}.musicxml"), "wb") as handle:
            handle.write(data)
        score = parse_xml_bytes(data)
        events = events_from_midi(spec) if spec["source"]["kind"] == CPM else events_from_score(score, spec)
        if spec["source"]["kind"] == CPM:
            primary = collections.Counter(event[2] for event in events)
        else:
            primary = pitch_bag(spec["source"]["kind"], spec["source"]["path"], *spec["bars"])
        checks = verify(spec, primary)
        signature = score.recurse().getElementsByClass("TimeSignature").first()
        total = max((event[0] + event[1] for event in events), default=0)
        entry = {
            "id": spec["id"],
            "technique": spec["technique"],
            "composer": spec["composer"],
            "title": spec["title"],
            "bars": spec["bars"],
            "approx_bars": bool(spec["source"].get("approx_bars")),
            "hand": spec["hand"],
            "marking": spec["marking"],
            "tempo": spec["tempo"],
            "time_signature": signature.ratioString if signature else None,
            "note": spec["note"],
            "source": {"kind": spec["source"]["kind"], "edition": spec["source"]["edition"]},
            "checks": checks,
            "manual_check": spec.get("manual_check"),
            "score": f"{spec['id']}.musicxml",
            "length": round(total, 4),
            "events": events,
        }
        index["excerpts"][spec["id"]] = entry
        index["techniques"].setdefault(spec["technique"], []).append(spec["id"])
        print(f"{spec['id']:40s} events={len(events):4d} checks={checks}")
    with open(os.path.join(out_dir, "index.json"), "w", encoding="utf-8") as handle:
        json.dump(index, handle, ensure_ascii=False, separators=(",", ":"))


ROOTS = {}

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--asap", required=True)
    parser.add_argument("--chopin", required=True)
    parser.add_argument("--cpm", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    ROOTS.update({ASAP: args.asap, CHOPIN_FE: args.chopin, CPM: args.cpm})
    build(args.out)
