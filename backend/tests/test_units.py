import io
import uuid

import pytest

from app.core.storage import (
    AUDIO_TYPES,
    PDF_TYPES,
    FileTooLarge,
    LocalStorage,
    UnsupportedMediaType,
    ensure_media_type,
)
from app.services.analyzers import Analyzer


def test_detect_measures_single_and_range():
    assert Analyzer.detect_measures("bars 25-48 are hard") == [(25, 48)]
    assert Analyzer.detect_measures("measure 60 needs work") == [(60, 60)]
    assert Analyzer.detect_measures("mm. 12 to 20") == [(12, 20)]
    assert Analyzer.detect_measures("nothing here") == []


def test_detect_measures_normalises_reversed_range():
    assert Analyzer.detect_measures("bars 48-25") == [(25, 48)]


def test_detect_techniques():
    found = Analyzer.detect_techniques("the double thirds and the leaps are rough, pedal is muddy")
    assert "Double thirds" in found
    assert "Wide leaps" in found
    assert "Half pedalling" in found
    assert all(0 < weight <= 1 for weight in found.values())


def test_media_type_guard():
    assert ensure_media_type("application/pdf", PDF_TYPES, "a PDF") == "application/pdf"
    assert ensure_media_type("audio/wav; codecs=1", AUDIO_TYPES, "audio") == "audio/wav"
    with pytest.raises(UnsupportedMediaType):
        ensure_media_type("text/plain", PDF_TYPES, "a PDF")


def test_local_storage_round_trip(tmp_path):
    storage = LocalStorage(root=str(tmp_path))
    key = storage.build_key(uuid.uuid4(), "scores", "etude.pdf")
    assert key.endswith(".pdf")
    written = storage.save(io.BytesIO(b"hello score"), key)
    assert written == 11
    assert storage.exists(key)
    with storage.open(key) as handle:
        assert handle.read() == b"hello score"
    assert storage.delete(key)
    assert not storage.exists(key)


def test_local_storage_rejects_oversized_file(tmp_path):
    storage = LocalStorage(root=str(tmp_path), max_bytes=10)
    key = storage.build_key(uuid.uuid4(), "scores", "big.pdf")
    with pytest.raises(FileTooLarge):
        storage.save(io.BytesIO(b"x" * 100), key)
    assert not storage.exists(key)


def test_local_storage_blocks_path_escape(tmp_path):
    storage = LocalStorage(root=str(tmp_path))
    with pytest.raises(Exception):
        storage.path_for("../../etc/passwd")
