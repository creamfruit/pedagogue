import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models.models import ReferenceTrack
from tests.test_keyboard_api import client, needs_db, perform, world  # noqa: F401
from tests.test_score_library import octave_study_xml

PITCHES = [60, 62, 64, 65, 67, 69, 71, 72, 71, 69, 67, 65]


def vlq(value):
    out = [value & 0x7F]
    value >>= 7
    while value:
        out.append((value & 0x7F) | 0x80)
        value >>= 7
    return bytes(reversed(out))


def make_midi(pitches, tempo=100, ticks=480):
    track = b"\x00\xff\x58\x04\x04\x02\x18\x08" + b"\x00\xff\x51\x03" + int(60_000_000 / tempo).to_bytes(3, "big")
    for pitch in pitches:
        track += vlq(0) + bytes([0x90, pitch, 80]) + vlq(ticks) + bytes([0x80, pitch, 0])
    track += b"\x00\xff\x2f\x00"
    header = b"MThd" + (6).to_bytes(4, "big") + (0).to_bytes(2, "big") + (1).to_bytes(2, "big") + ticks.to_bytes(2, "big")
    return header + b"MTrk" + len(track).to_bytes(4, "big") + track


def upload(http, entry, name, data, kind="audio/midi"):
    return http.post(f"/api/v1/keyboard/entries/{entry}/reference", files={"file": (name, data, kind)})


async def track_row(world, entry):
    async with world.factory() as session:
        return (await session.execute(select(ReferenceTrack).where(ReferenceTrack.repertoire_entry_id == entry))).scalar_one_or_none()


def test_the_midi_writer_makes_files_the_importer_recognises():
    from app.core.storage import sniff_score

    assert sniff_score(make_midi(PITCHES)[:64], "tune.mid") == "midi"


@needs_db
async def test_a_midi_file_becomes_the_reference_for_a_piece_without_one(world):
    async with client() as http:
        before = (await http.get(f"/api/v1/keyboard/entries/{world.ids.bare}/reference")).json()
        assert before["available"] is False and before["attached"] is None
        response = await upload(http, world.ids.bare, "tune.mid", make_midi(PITCHES))
        assert response.status_code == 201, response.text
        data = response.json()
        assert data["available"] is True and data["source"] == "midi"
        assert data["attached"]["filename"] == "tune.mid" and data["attached"]["source"] == "midi"
        assert (data["first_bar"], data["last_bar"], data["beats_per_bar"], data["note_count"]) == (1, 3, 4, 12)
        assert data["quarter_bpm"] == pytest.approx(100, abs=1)
        notes = (await http.get(f"/api/v1/keyboard/entries/{world.ids.bare}/reference/notes", params={"start_bar": 2, "end_bar": 2})).json()
        assert [note[1] for note in notes["notes"]] == [67, 69, 71, 72]
        assert [note[0] for note in notes["notes"]] == [0.0, 1.0, 2.0, 3.0]
    row = await track_row(world, world.ids.bare)
    assert row.note_count == 12 and row.bar_count == 3 and row.storage_key.startswith(f"midi/{world.ids.user}/")
    assert world.storage.exists(row.storage_key)


@needs_db
async def test_a_run_can_be_scored_against_an_attached_midi_file(world):
    async with client() as http:
        await upload(http, world.ids.bare, "tune.mid", make_midi(PITCHES))
        notes = (await http.get(f"/api/v1/keyboard/entries/{world.ids.bare}/reference/notes", params={"start_bar": 1, "end_bar": 3})).json()["notes"]
        body = {"mode": "scored", "start_bar": 1, "end_bar": 3, "tempo_bpm": 90, "duration_sec": 15, "notes": perform(notes, 90)}
        data = (await http.post(f"/api/v1/keyboard/entries/{world.ids.bare}/attempts", json=body)).json()
        assert data["accuracy"] == 1.0 and data["clean"] is True
        assert [bar["bar"] for bar in data["bars"]] == [1, 2, 3]


@needs_db
async def test_attaching_another_file_replaces_the_first_and_removes_it_from_storage(world):
    async with client() as http:
        await upload(http, world.ids.bare, "first.mid", make_midi(PITCHES))
        first = await track_row(world, world.ids.bare)
        response = await upload(http, world.ids.bare, "second.mid", make_midi(PITCHES[:8]))
        assert response.status_code == 201
        assert response.json()["attached"]["filename"] == "second.mid" and response.json()["note_count"] == 8
    second = await track_row(world, world.ids.bare)
    assert second.id != first.id
    assert not world.storage.exists(first.storage_key) and world.storage.exists(second.storage_key)
    async with world.factory() as session:
        count = (await session.execute(select(func.count()).select_from(ReferenceTrack).where(ReferenceTrack.repertoire_entry_id == world.ids.bare))).scalar_one()
        assert count == 1


@needs_db
async def test_an_attached_file_wins_over_an_uploaded_score_until_it_is_removed(world):
    async with client() as http:
        uploaded = (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/reference")).json()
        assert uploaded["source"] == "musicxml" and uploaded["attached"] is None and uploaded["last_bar"] == 12
        attached = (await upload(http, world.ids.entry, "tune.mid", make_midi(PITCHES))).json()
        assert attached["source"] == "midi" and attached["last_bar"] == 3
        removed = await http.delete(f"/api/v1/keyboard/entries/{world.ids.entry}/reference")
        assert removed.status_code == 204
        back = (await http.get(f"/api/v1/keyboard/entries/{world.ids.entry}/reference")).json()
        assert back["source"] == "musicxml" and back["attached"] is None
    assert await track_row(world, world.ids.entry) is None


@needs_db
async def test_removing_a_file_deletes_it_and_the_piece_loses_note_checking(world):
    async with client() as http:
        await upload(http, world.ids.bare, "tune.mid", make_midi(PITCHES))
        row = await track_row(world, world.ids.bare)
        assert (await http.delete(f"/api/v1/keyboard/entries/{world.ids.bare}/reference")).status_code == 204
        assert not world.storage.exists(row.storage_key)
        assert (await http.get(f"/api/v1/keyboard/entries/{world.ids.bare}/reference")).json()["available"] is False
        again = await http.delete(f"/api/v1/keyboard/entries/{world.ids.bare}/reference")
        assert again.status_code == 404


@needs_db
async def test_musicxml_files_can_be_attached_too(world):
    async with client() as http:
        response = await upload(http, world.ids.bare, "study.musicxml", octave_study_xml(), "application/xml")
        assert response.status_code == 201, response.text
        assert response.json()["source"] == "musicxml" and response.json()["last_bar"] == 12


@needs_db
async def test_files_that_are_not_readable_scores_are_refused_without_leaving_anything_behind(world):
    empty = make_midi([])
    async with client() as http:
        pdf = await upload(http, world.ids.bare, "score.pdf", b"%PDF-1.7 " + b"0" * 40, "application/pdf")
        assert pdf.status_code == 415 and "MIDI" in pdf.json()["detail"]
        junk = await upload(http, world.ids.bare, "tune.mid", b"this is not a midi file at all")
        assert junk.status_code == 415
        none = await upload(http, world.ids.bare, "empty.mid", empty)
        assert none.status_code == 422 and "Couldn't read any notes" in none.json()["detail"]
        broken = await upload(http, world.ids.bare, "broken.mid", b"MThd\x00\x00\x00\x06\x00\x01\x00\x01\x01\xe0MTrk\x00\x00\x00\x09garbage!!")
        assert broken.status_code == 422
    assert await track_row(world, world.ids.bare) is None
    assert list(world.storage.root.rglob("*.mid")) == []


@needs_db
async def test_a_full_upload_quota_refuses_the_file(world, monkeypatch):
    monkeypatch.setattr(settings, "upload_quota_mb", 0)
    async with client() as http:
        response = await upload(http, world.ids.bare, "tune.mid", make_midi(PITCHES))
    assert response.status_code == 413 and "upload space" in response.json()["detail"]
    assert await track_row(world, world.ids.bare) is None


@needs_db
async def test_other_peoples_pieces_cannot_be_given_a_reference(world):
    async with client() as http:
        world.current.id = world.ids.other
        assert (await upload(http, world.ids.bare, "tune.mid", make_midi(PITCHES))).status_code == 404
        assert (await http.delete(f"/api/v1/keyboard/entries/{world.ids.bare}/reference")).status_code == 404
    assert await track_row(world, world.ids.bare) is None
