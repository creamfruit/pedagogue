import copy
from lxml import etree

DROP_TAGS = {"print", "credit", "identification", "defaults", "work", "movement-number", "movement-title"}

def _strip_layout(el):
    for node in list(el.iter()):
        if not isinstance(node.tag, str):
            continue
        for attr in ("default-x", "default-y", "relative-x", "relative-y", "width"):
            if attr in node.attrib and node.tag != "note":
                del node.attrib[attr]
            elif attr in node.attrib and node.tag == "note" and attr in ("default-x", "default-y"):
                del node.attrib[attr]

def slice_xml(src_bytes, start, end, keep_staves=None):
    root = etree.fromstring(src_bytes)
    if root.tag != "score-partwise":
        raise ValueError("expected score-partwise")
    for tag in DROP_TAGS:
        for node in root.findall(tag):
            root.remove(node)
    for part in root.findall("part"):
        state = {"divisions": None, "key": None, "time": None, "staves": None, "clef": {}, "shift": {}}
        new_measures = []
        phase = "before"
        for measure in list(part.findall("measure")):
            number = measure.get("number", "")
            digits = "".join(ch for ch in number if ch.isdigit())
            num = int(digits) if digits and digits == number.strip() else None
            if phase == "before" and num == start:
                phase = "inside"
            elif phase == "inside" and num is not None and num > end:
                phase = "after"
            elif phase == "inside" and num is not None and num < start:
                phase = "after"
            if phase == "before":
                for attrs in measure.findall("attributes"):
                    for child in attrs:
                        if child.tag == "divisions":
                            state["divisions"] = copy.deepcopy(child)
                        elif child.tag == "key":
                            state["key"] = copy.deepcopy(child)
                        elif child.tag == "time":
                            state["time"] = copy.deepcopy(child)
                        elif child.tag == "staves":
                            state["staves"] = copy.deepcopy(child)
                        elif child.tag == "clef":
                            state["clef"][child.get("number", "1")] = copy.deepcopy(child)
                for direction in measure.findall("direction"):
                    for shift in direction.iter("octave-shift"):
                        staff = direction.findtext("staff") or "1"
                        key = (staff, shift.get("number", "1"))
                        if shift.get("type") in ("up", "down"):
                            state["shift"][key] = (shift.get("type"), shift.get("size", "8"))
                        elif shift.get("type") == "stop":
                            state["shift"].pop(key, None)
                part.remove(measure)
            elif phase == "inside":
                new_measures.append(measure)
                if num == end:
                    phase = "closing"
            elif phase == "closing":
                if num is None or num == end:
                    new_measures.append(measure)
                else:
                    phase = "after"
                    part.remove(measure)
            else:
                part.remove(measure)
        if not new_measures:
            continue
        first = new_measures[0]
        existing = first.find("attributes")
        merged = etree.Element("attributes")
        present = {child.tag for child in existing} if existing is not None else set()
        present_clefs = {c.get("number", "1") for c in existing.findall("clef")} if existing is not None else set()
        for tag in ("divisions", "key", "time", "staves"):
            if state[tag] is not None and tag not in present:
                merged.append(state[tag])
        for number, clef in sorted(state["clef"].items()):
            if number not in present_clefs:
                merged.append(clef)
        if existing is not None:
            for child in list(existing):
                merged.append(child)
            first.remove(existing)
        order = ["footnote", "level", "divisions", "key", "time", "staves", "part-symbol", "instruments", "clef", "staff-details", "transpose", "directive", "measure-style"]
        children = sorted(list(merged), key=lambda c: order.index(c.tag) if c.tag in order else 99)
        for child in list(merged):
            merged.remove(child)
        for child in children:
            merged.append(child)
        first.insert(0, merged)
        insert_at = 1
        for (staff, number), (kind, size) in state["shift"].items():
            direction = etree.Element("direction")
            dtype = etree.SubElement(direction, "direction-type")
            etree.SubElement(dtype, "octave-shift", type=kind, size=size, number=number)
            etree.SubElement(direction, "staff").text = staff
            first.insert(insert_at, direction)
            insert_at += 1
        for measure in new_measures:
            for node in measure.findall("print"):
                measure.remove(node)
            for barline in measure.findall("barline"):
                if barline.find("repeat") is not None or barline.find("ending") is not None:
                    measure.remove(barline)
        active = dict(state["shift"])
        for measure in new_measures:
            for direction in measure.findall("direction"):
                for shift in direction.iter("octave-shift"):
                    staff = direction.findtext("staff") or "1"
                    key = (staff, shift.get("number", "1"))
                    if shift.get("type") in ("up", "down"):
                        active[key] = (shift.get("type"), shift.get("size", "8"))
                    elif shift.get("type") == "stop":
                        active.pop(key, None)
        last = new_measures[-1]
        for (staff, number), (kind, size) in active.items():
            direction = etree.SubElement(last, "direction")
            dtype = etree.SubElement(direction, "direction-type")
            etree.SubElement(dtype, "octave-shift", type="stop", size=size, number=number)
            etree.SubElement(direction, "staff").text = staff
        for old in last.findall("barline"):
            if old.get("location", "right") == "right":
                last.remove(old)
        barline = etree.SubElement(last, "barline", location="right")
        etree.SubElement(barline, "bar-style").text = "light-heavy"
    _strip_layout(root)
    for node in root.iter("sound"):
        pass
    return etree.tostring(root, xml_declaration=True, encoding="UTF-8", doctype='<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">')
