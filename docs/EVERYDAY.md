# Everyday work: helpers, documents, saving answers

## Helpers

A helper is the same AI prepared for one kind of job: a role, a tone and a few example
questions. Datas ships 43 in five groups (every day, work, study, technical, creative), in
English and Spanish — *Explain it simply*, *Summarize*, *Business emails*, *Spreadsheets and
finance*, *Presentations*, *School homework*, *Work with my documents*… Pick one from the
chat's top bar, or chat without any.

**Make my own helper**: a name, what it should do in your own words, optional example
questions, and optional reference documents (a price list, a manual, house rules). It is saved
in `<data folder>/assistants/` and appears under *Mine*.

The **Datas guide** is a special helper that knows this device: what it can run, which AI
suits which task, where to click. It answers even before any AI is installed.

## Documents and pictures in a chat

Attach with the paperclip, drag a file onto the chat, or paste.

- **Documents**: PDF, Word (.docx), Excel (.xlsx), PowerPoint (.pptx), web pages, and plain
  text of many kinds (notes, code, CSV…). Datas turns them into text on the device. For each
  question it hands the AI the passages that match, as many as fit in what the AI can keep in
  mind, so a long document does not crowd out the conversation.
- **Pictures**: for AIs that understand pictures (marked in *Add an AI*). Pictures are made
  smaller before being shown to the AI.

A scanned PDF with no text layer has nothing to extract: attach its pages as pictures to an
AI that understands pictures, or let the agent run an OCR (text recognition) program such as
Tesseract when it is installed.

## Saving an answer as a file

Under every answer: **Copy**, **Read aloud**, **Save as**.

| Format | What you get |
|---|---|
| Word (.docx) | headings, lists, tables, bold and italics as real Word formatting |
| Excel (.xlsx) | each table as a sheet; cells that start with `=` stay as formulas |
| PowerPoint (.pptx) | one slide per heading, bullets as bullets; a paragraph that starts with `Notes:` becomes the speaker notes |
| PDF | a clean printable page |
| Web page (.html), Markdown (.md), text (.txt) | for publishing or further editing |

Files go to **Documents/Datas** (or the data folder's `exports/` in a portable copy). The
notice that appears offers *Open* and *Show in folder*. Code blocks have their own *Save as
file*, with the right ending for the language.

## Everyday tools (Tools screen)

| Tool | Does | Needs |
|---|---|---|
| Recording to text | a meeting, class, voice note or video becomes text with timestamps, plus a subtitles file (.srt) | voice installed; FFmpeg for formats other than WAV (Datas fetches a copy if none is found) |
| Text to audio | a text becomes a WAV file, and an MP3 when FFmpeg is available | voice installed |
| Long documents | summary or translation of a document of any length, piece by piece, then joined | an AI running |

Code: [`datas/assistants/`](../datas/assistants), [`datas/docs.py`](../datas/docs.py),
[`datas/export.py`](../datas/export.py), [`datas/tools.py`](../datas/tools.py).
