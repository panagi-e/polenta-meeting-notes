# Changes

Newest first. "Runtime" is the backend version the app sets up; a new runtime means the app shows
the setup screen once after updating, and you click **Set up the backend** then **Continue**.

## 2026-10-28: library search finds what was actually said (runtime 39)

Library chat could miss things that were plainly discussed. Asking "What are the issues with
Turkey?" in a folder returned nothing, though Turkey had come up on a call the week before: the
name was said in passing, and what went wrong was explained in the next stretch of conversation.

- **Summaries and your notes are searchable**, not just transcripts. The index is updated when a
  summary is written or edited and when notes are saved.
- **Passages are about a minute of conversation** (around 150 words, speakers named) instead of
  single turns, so fragments such as "issue." no longer crowd out real answers.
- **Exact words count as well as meaning.** Search matches the words of your question alongside
  its meaning, and the best exact matches always make the cut, so a name such as a country, a
  system or a person is found even when the conversation around it was about something else.
- **The best passages come with what was said either side** before the answer is written.
- **Answers are more careful**: a passage is linked to your subject only when it makes that link
  itself, and hypothetical examples are reported as examples.

On the real vault, 8 of 9 test questions now reach the answer, up from 3 of 9, and the Turkey
question returns the failed Turkey Finance org-chart upload and the PowerPoint size limit behind
it. After updating, the search index is rebuilt once in the background (about 4 minutes for 186
meetings); search keeps working on the old index until it is done.

## 2026-10-26: the app is responsive again after long uptime

Switching to the window, opening a meeting and dropping in a recording could each take seconds.
Idle redraws, where unchanged status updates re-rendered the whole window, are gone, so the app
stays quick however long it has been running.

## 2026-09-28: a pop-up asks to record when a meeting starts

When a calendar meeting is due, or a call app such as Teams or Zoom starts using the microphone,
a small pop-up in the top-right corner asks whether to record. It floats over full-screen calls
without taking focus, and recording starts only when you click. It can be turned off in Settings.

## 2026-09-22: import written transcripts (runtime 38)

Drop a transcript (.md, .vtt or .srt) on the window and it is processed like a recording:
speakers, summary, folder suggestion and search. Transcripts from Granola, the Insta360 Wave and
similar tools are read, including their cue numbers and heading lines, and Granola's "Me" is
mapped to you.
