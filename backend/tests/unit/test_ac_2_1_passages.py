"""Section 2.1: how meetings are cut into passages for library search, and how
keyword and meaning rankings are fused."""

from meetingnotes.pipeline.segments import Segment
from meetingnotes.vectors.chunking import (
    MAX_WORDS,
    MIN_WORDS,
    TARGET_WORDS,
    chunk_notes,
    chunk_segments,
    chunk_summary,
)
from meetingnotes.vectors.store import fuse_rankings


def turn(i, speaker, words):
    text = " ".join(f"w{i}x{n}" for n in range(words))
    return Segment(start=float(i * 10), end=float(i * 10 + 9), speaker=speaker, text=text)


def test_turns_are_grouped_into_runs_with_speakers_named():
    """Passages are runs of consecutive turns of about TARGET_WORDS, not one
    fragment per turn, and each line still says who spoke."""
    segments = [turn(i, "Ben" if i % 2 else "Martin", 30) for i in range(20)]  # 600 words
    chunks = chunk_segments(segments)

    assert 3 <= len(chunks) <= 5
    for chunk in chunks:
        assert len(chunk.text.split()) <= MAX_WORDS + 2 * 10  # labels add a word a line
        assert chunk.text.startswith(("Martin: ", "Ben: "))
        assert chunk.speaker in ("Martin, Ben", "Ben, Martin")
        assert chunk.start_s < chunk.end_s
    assert [c.seq for c in chunks] == list(range(len(chunks)))
    # Nothing lost, nothing repeated: every turn lands in exactly one passage.
    joined = "\n".join(c.text for c in chunks)
    for i in range(20):
        assert joined.count(f"w{i}x0 ") == 1


def test_a_turn_is_never_split_unless_it_is_too_long_on_its_own():
    segments = [turn(0, "Martin", 100), turn(1, "Ben", 100), turn(2, "Martin", 400)]
    chunks = chunk_segments(segments)
    # The 400-word turn is split into pieces; the 100-word turns stay whole.
    whole = [c for c in chunks if "w0x0 " in c.text or "w1x0 " in c.text]
    for c in whole:
        if "w0x0 " in c.text:
            assert "w0x99" in c.text
    assert sum("w2x" in c.text for c in chunks) >= 2


def test_filler_never_stands_alone():
    """One-word turns ("issue.", "Yeah.") join the passage beside them rather
    than becoming passages that crowd out real ones."""
    segments = [
        Segment(start=0, end=1, speaker="Martin", text="Yeah."),
        Segment(start=1, end=2, speaker="Ben", text="issue."),
        turn(2, "Martin", TARGET_WORDS + 10),
        Segment(start=40, end=41, speaker="Ben", text="Okay, thanks."),
    ]
    chunks = chunk_segments(segments)
    assert all(len(c.text.split()) >= MIN_WORDS for c in chunks)
    assert "Martin: Yeah." in chunks[0].text and "Ben: issue." in chunks[0].text
    assert chunks[-1].text.endswith("Ben: Okay, thanks.")


def test_a_short_meeting_is_still_one_passage():
    chunks = chunk_segments([Segment(start=0, end=3, speaker="Ben", text="Budget approved.")])
    assert len(chunks) == 1 and chunks[0].text == "Ben: Budget approved."


SUMMARY = """## Core items discussed

**System maintenance and support gaps**
- A failed upload for the Turkey Finance org chart, likely a PowerPoint over the size limit.
- There is no designated owner for the GERA platform, and support tickets go unanswered.

## Next Steps

- Forward the Turkish Finance upload email to Martin and Marika Jansen for review.
"""


def test_summary_sections_become_titled_passages():
    chunks = chunk_summary(SUMMARY, title="Ken call")
    assert len(chunks) == 2
    assert chunks[0].text.startswith("Summary (Ken call - Core items discussed):")
    assert "Turkey Finance org chart" in chunks[0].text
    assert chunks[1].text.startswith("Summary (Ken call - Next Steps):")
    assert {c.source for c in chunks} == {"summary"}
    assert [c.seq for c in chunks] == [0, 1]


def test_placeholder_and_empty_summaries_are_not_indexed():
    assert chunk_summary("_Imported transcript; the summary is being written._") == []
    assert chunk_summary("") == []
    assert chunk_summary("Too short.") == []


def test_notes_are_packed_on_paragraphs():
    notes = "\n\n".join(f"Paragraph {i} " + "word " * 60 for i in range(5))
    chunks = chunk_notes(notes)
    assert 2 <= len(chunks) <= 3
    assert {c.source for c in chunks} == {"notes"}
    assert all(c.speaker == "Your notes" for c in chunks)


def test_fusion_lifts_a_passage_that_ranks_in_both_lists():
    def row(seq):
        return {"meeting_id": "m", "source": "transcript", "seq": seq}

    by_vector = [row(1), row(2), row(3)]
    by_text = [row(9), row(3)]
    fused = fuse_rankings([by_vector, by_text], limit=3)
    assert [r["seq"] for r in fused][0] == 3, "near the top of both beats the top of one"
    assert {r["seq"] for r in fused} <= {1, 2, 3, 9}
    assert fused[0]["_fused"] > fused[1]["_fused"]
