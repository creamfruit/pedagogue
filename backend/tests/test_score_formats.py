import asyncio
import io
import zipfile

import pytest

from app.core.storage import LocalStorage, UnsupportedMediaType, score_format, sniff_score
from app.models.models import PdfSubmission
from app.services.analyzers import ScoreAnalyzer

MUSICXML = b"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE score-partwise PUBLIC "-//Recordare//DTD MusicXML 4.0 Partwise//EN" "http://www.musicxml.org/dtds/partwise.dtd">
<score-partwise version="4.0">
  <part-list><score-part id="P1"><part-name>Piano</part-name></score-part></part-list>
  <part id="P1"><measure number="1"/><measure number="2"/><measure number="3"/></part>
</score-partwise>
"""
MIDI = b"MThd\x00\x00\x00\x06\x00\x01\x00\x02\x01\xe0MTrk\x00\x00\x00\x00"


def mxl(inner=MUSICXML):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr(
            "META-INF/container.xml",
            '<container><rootfiles><rootfile full-path="score.xml"/></rootfiles></container>',
        )
        archive.writestr("score.xml", inner)
    return buffer.getvalue()


def test_formats_are_read_from_the_file_not_the_content_type():
    assert sniff_score(b"%PDF-1.7 ...", "scan.pdf") == "pdf"
    assert sniff_score(MUSICXML, "etude.musicxml") == "musicxml"
    assert sniff_score(b"\xef\xbb\xbf" + MUSICXML, "etude.xml") == "musicxml"
    assert sniff_score(mxl(), "etude.mxl") == "mxl"
    assert sniff_score(MIDI, "etude.mid") == "midi"
    assert sniff_score(MIDI, "no-extension") == "midi"


def test_other_files_are_refused():
    with pytest.raises(UnsupportedMediaType):
        sniff_score(b"<html><body>hi</body></html>", "page.xml")
    with pytest.raises(UnsupportedMediaType):
        sniff_score(mxl(), "archive.zip")
    with pytest.raises(UnsupportedMediaType):
        sniff_score(b"\x89PNG\r\n", "photo.png")


def test_score_format_leaves_the_stream_where_it_was():
    stream = io.BytesIO(MIDI)
    assert score_format(stream, "a.mid") == "midi"
    assert stream.tell() == 0


def analyse(tmp_path, name, data):
    storage = LocalStorage(root=str(tmp_path))
    storage.save(io.BytesIO(data), name)
    submission = PdfSubmission(storage_key=name)
    return submission, asyncio.run(ScoreAnalyzer(None, storage).analyze(submission))


def test_musicxml_scores_are_counted(tmp_path):
    submission, result = analyse(tmp_path, "musicxml/u/a.musicxml", MUSICXML)
    assert result.raw["format"] == "musicxml"
    assert result.raw["bars"] == 3 and result.raw["parts"] == 1
    assert submission.needs_review is False


def test_compressed_musicxml_is_unpacked(tmp_path):
    _, result = analyse(tmp_path, "musicxml/u/a.mxl", mxl())
    assert result.raw["compressed"] is True
    assert result.raw["bars"] == 3


def test_midi_tracks_are_read(tmp_path):
    submission, result = analyse(tmp_path, "midi/u/a.mid", MIDI)
    assert result.raw["format"] == "midi"
    assert result.raw["tracks"] == 2
    assert submission.page_count is None
