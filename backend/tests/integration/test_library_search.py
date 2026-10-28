"""Library search over real LanceDB: keyword matches fused with meaning, the
summary and notes searchable, hits widened with their neighbours, and the
one-off rebuild of an existing vault onto the current index.

The embedder here is deliberately blind to the word that matters ("Turkey"),
standing in for a semantic model that gives a name no special weight, so the
tests show what the keyword half of the search adds."""

import numpy as np
import pytest

from meetingnotes.llm.librarychat import ChatScope, ask_library, build_excerpts, retrieve
from meetingnotes.pipeline.segments import SegmentList, save_segments
from meetingnotes.storage import folders as f
from meetingnotes.storage import meetings as m
from meetingnotes.storage.frontmatter import write_meeting_md
from meetingnotes.vectors.indexer import backfill_index, index_meeting
from meetingnotes.vectors.store import LEGACY_TABLE, VectorStore
from tests.conftest import FakeLMClient, make_meeting


class IssueEmbedder:
    """Knows only the words "issue" and "problem": every passage about
    issues looks alike, and Turkey means nothing to it."""

    def embed_texts(self, texts):
        vectors = []
        for text in texts:
            lowered = text.lower()
            vector = np.array([
                1.0 if "issue" in lowered else 0.0,
                1.0 if "problem" in lowered else 0.0,
                0.1,
            ])
            vectors.append(vector / np.linalg.norm(vector))
        return np.array(vectors)


def padding(word, n):
    return " ".join(f"{word}{i}" for i in range(n))


def seed(conn, vault, meeting_id, title, folder_id, turns, summary=None):
    make_meeting(conn, vault, meeting_id, title)
    m.set_folder(conn, meeting_id, folder_id)
    save_segments(SegmentList(segments=[
        {"start": float(i * 30), "end": float(i * 30 + 25), "speaker": s, "text": t}
        for i, (s, t) in enumerate(turns)
    ]), vault.meeting_dir(meeting_id) / "segments.json")
    if summary:
        write_meeting_md(vault.meeting_md_path(meeting_id), {"id": meeting_id, "title": title},
                         summary)
    return meeting_id


@pytest.fixture
def dp(conn):
    return f.create_folder(conn, "DP")


@pytest.fixture
def turkey_call(conn, vault, dp):
    """The real case: Turkey is named in passing, and what went wrong is said
    in the next stretch of conversation and in the summary."""
    return seed(conn, vault, "2026-10-12_1609_ken-call", "Ken call", dp, [
        ("Martin", padding("chatter", 140) + " someone does not have a link they need"),
        ("Ken", "And that is to do with Turkey Finance org chart."),
        ("Ken", "The upload failed because the PowerPoint was over the size limit. "
         + padding("detail", 150)),
        ("Martin", padding("later", 160)),
    ], summary="## Core items discussed\n\n- A failed upload for the Turkey Finance org "
               "chart, likely a PowerPoint over the size limit.\n")


@pytest.fixture
def issue_noise(conn, vault, dp):
    """Other DP meetings full of the word "issue", which a meaning-only
    search ranks first for any question about issues."""
    ids = []
    for n in range(6):
        ids.append(seed(conn, vault, f"2026-10-0{n}_1000_noise", f"Noise {n}", dp, [
            ("Ben", "We have a lot of issues. That is an issue. Another issue. "
             + padding(f"n{n}w", 150)),
            ("Ben", "issue. problem. " + padding(f"m{n}w", 150)),
        ]))
    return ids


def test_a_name_is_found_even_when_meaning_search_misses_it(
        conn, vault, dp, turkey_call, issue_noise):
    store, embedder = VectorStore(vault.lancedb_dir), IssueEmbedder()
    for meeting_id in [turkey_call, *issue_noise]:
        index_meeting(conn, vault, store, embedder, meeting_id)
    question = "What are the issues with Turkey?"

    # Meaning alone: every passage about "issues" outranks the one that
    # names Turkey, so it is not retrieved at all.
    vector_only = store.search(embedder.embed_texts([question])[0], folder_id=dp, limit=12)
    assert not any("Turkey" in r["chunk_text"] for r in vector_only)

    # With the question's words fused in, the Turkey passages are retrieved:
    # the transcript passage and the summary passage.
    hits = retrieve(store, embedder, question, ChatScope.FOLDER, dp)
    turkey = [h for h in hits if "Turkey" in h["chunk_text"]]
    assert {h["source"] for h in turkey} == {"transcript", "summary"}


def test_the_answer_sees_what_was_said_around_the_hit(conn, vault, dp, turkey_call, issue_noise):
    """The passage naming Turkey is widened with the next one, where the
    PowerPoint problem is actually described, and the summary is sent too."""
    store, embedder = VectorStore(vault.lancedb_dir), IssueEmbedder()
    for meeting_id in [turkey_call, *issue_noise]:
        index_meeting(conn, vault, store, embedder, meeting_id)

    client = FakeLMClient(f"The Turkey upload failed.\n\nSources: {turkey_call}")
    result = ask_library(client, store, embedder, "What are the issues with Turkey?",
                         scope=ChatScope.FOLDER, folder_id=dp)

    sent = client.requests[0][-1]["content"]
    assert "Turkey Finance org chart" in sent
    assert "the PowerPoint was over the size limit" in sent, "the neighbour came with it"
    assert f"[meeting {turkey_call}] Summary:" in sent
    assert f"[meeting {turkey_call}] Transcript from" in sent
    assert result.citations == [turkey_call]


def test_adjacent_passages_merge_and_the_budget_holds(conn, vault, dp, turkey_call):
    store, embedder = VectorStore(vault.lancedb_dir), IssueEmbedder()
    index_meeting(conn, vault, store, embedder, turkey_call)
    rows = [r for r in store.rows_for_meeting(turkey_call) if r["source"] == "transcript"]
    rows.sort(key=lambda r: r["seq"])

    # Two neighbouring hits become one excerpt, not two overlapping ones.
    excerpts = build_excerpts(store, [rows[0], rows[1]])
    transcript = [e for e in excerpts if e.label.startswith("Transcript")]
    assert len(transcript) == 1
    assert transcript[0].text.count("Turkey Finance org chart") == 1

    # A tiny budget still sends the best excerpt, and nothing more.
    assert len(build_excerpts(store, rows, budget_words=10)) == 1


def test_notes_are_searchable(conn, vault, dp, issue_noise):
    from meetingnotes.notes.notes import write_notes

    store, embedder = VectorStore(vault.lancedb_dir), IssueEmbedder()
    meeting_id = seed(conn, vault, "2026-10-20_0900_board", "Board", dp,
                      [("Ben", padding("talk", 60))])
    write_notes(vault, meeting_id, "Remember: the Istanbul office lease renews in March, "
                                   "and legal must review it first.")
    for mid in [meeting_id, *issue_noise]:
        index_meeting(conn, vault, store, embedder, mid)

    hits = retrieve(store, embedder, "When does the Istanbul lease renew?", ChatScope.FOLDER, dp)
    notes = [h for h in hits if h["source"] == "notes"]
    assert notes and "Istanbul office lease" in notes[0]["chunk_text"]


def test_a_silent_meetings_stock_note_is_not_indexed(conn, vault, dp):
    from meetingnotes.llm.summary import NO_SPEECH_BODY

    store, embedder = VectorStore(vault.lancedb_dir), IssueEmbedder()
    meeting_id = seed(conn, vault, "2026-10-21_0900_silent", "Silent", dp, [],
                      summary=NO_SPEECH_BODY)
    assert index_meeting(conn, vault, store, embedder, meeting_id) == 0


# -- the one-off rebuild ------------------------------------------------------

def seed_legacy_table(store, meeting_id, folder_id):
    """A row as the first index version wrote it: one per turn, no source."""
    store._db.create_table(LEGACY_TABLE, data=[{
        "meeting_id": meeting_id, "folder_id": folder_id,
        "chunk_text": "And that is to do with Turkey Finance org chart.",
        "speaker": "Ken", "start_s": 30.0, "end_s": 33.0, "vector": [0.0, 0.0, 1.0],
    }])


def test_search_keeps_working_during_the_rebuild_then_switches(
        conn, vault, dp, turkey_call, issue_noise):
    store, embedder = VectorStore(vault.lancedb_dir), IssueEmbedder()
    seed_legacy_table(store, turkey_call, dp)
    assert not store.ready

    # Before the rebuild: the old table answers, so search is never blank.
    before = retrieve(store, embedder, "Turkey", ChatScope.FOLDER, dp)
    assert before and "source" not in before[0]

    # Interrupted after one meeting: progress is kept and search stays on
    # the old table until every meeting is in.
    calls = iter([False, True])
    assert backfill_index(conn, vault, store, embedder, stop=lambda: next(calls)) == 1
    assert not store.ready
    assert len(store.indexed_meeting_ids()) == 1

    # Resumed: the rest are indexed, search switches over, the old table goes.
    assert backfill_index(conn, vault, store, embedder) == len(issue_noise)
    assert store.ready
    assert LEGACY_TABLE not in store._db.table_names()
    after = retrieve(store, embedder, "What are the issues with Turkey?", ChatScope.FOLDER, dp)
    assert any(h["source"] == "summary" and "Turkey" in h["chunk_text"] for h in after)

    # A finished rebuild is a no-op on the next start.
    assert backfill_index(conn, vault, store, embedder) == 0


def test_a_fresh_vault_needs_no_rebuild(vault):
    assert VectorStore(vault.lancedb_dir).ready


# -- re-indexing as the meeting changes ---------------------------------------

def test_the_summary_is_indexed_once_it_is_written(conn, vault, stages, monkeypatch):
    """The embed stage runs before the summary exists, so the summarise
    stage indexes again; a failure there never fails the meeting."""
    from meetingnotes.config import default_config
    from meetingnotes.jobs.stages import build_stages

    calls = []
    meeting_id = make_meeting(conn, vault)
    vault.transcript_path(meeting_id).write_text("# Transcript\n")
    monkeypatch.setattr("meetingnotes.jobs.stages.summarise_meeting",
                        lambda *args, **kwargs: None)

    def indexer(mid):
        calls.append(mid)
        raise RuntimeError("index unavailable")

    real = build_stages(conn, vault, default_config(vault.root), engine=None,
                        speaker_embedder=None, lm_client=None, chunk_indexer=indexer)
    real["summarise"](meeting_id)  # does not raise
    assert calls == [meeting_id]


def test_editing_the_summary_reindexes_it(conn, vault, stages):
    import time

    import httpx
    from fastapi.testclient import TestClient

    from meetingnotes.api.app import AppState, create_app
    from meetingnotes.config import default_config
    from meetingnotes.enrolment.gallery import Gallery
    from meetingnotes.jobs.worker import Worker
    from meetingnotes.llm.client import LMStudioClient

    dp = f.create_folder(conn, "DP")
    store, embedder = VectorStore(vault.lancedb_dir), IssueEmbedder()
    meeting_id = seed(conn, vault, "2026-10-22_0900_ops", "Ops", dp,
                      [("Ben", padding("talk", 60))])
    app = create_app(AppState(
        conn=conn, vault=vault, config=default_config(vault.root),
        worker=Worker(conn, stages),
        lm_client=LMStudioClient(http=httpx.Client(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json={"data": []})))),
        gallery=Gallery(conn, vault), vector_store=store, text_embedder=embedder,
    ))
    with TestClient(app) as client:
        client.put(f"/meetings/{meeting_id}/summary",
                   json={"body": "## Decisions\n\n- The Ankara depot closes at the end of "
                                 "the quarter, agreed by everyone present."})
        client.put(f"/meetings/{meeting_id}/notes",
                   json={"text": "Call the Izmir team about the depot handover plan soon."})

    # The re-index runs off the request thread.
    for _ in range(50):
        sources = {r["source"] for r in store.rows_for_meeting(meeting_id)}
        if {"summary", "notes"} <= sources:
            break
        time.sleep(0.05)
    rows = store.rows_for_meeting(meeting_id)
    assert any(r["source"] == "summary" and "Ankara depot" in r["chunk_text"] for r in rows)
    assert any(r["source"] == "notes" and "Izmir team" in r["chunk_text"] for r in rows)
