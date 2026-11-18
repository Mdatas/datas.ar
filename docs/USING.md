# Using Datas: the window, helpers, documents

What each screen is for, and the everyday work around a chat: helpers, documents at hand,
saving and printing answers.

## The window

One window, a few screens, nothing loaded from outside the computer.

### Screens

| Screen | For |
|---|---|
| **Chat** (home) | Chats listed on the left with search; the top bar chooses the AI, a helper, and internet for this chat; answers can be stopped, copied, read aloud and saved as files. |
| **Add an AI** | What do you want to do, how much of the device may be used; a verdict for every AI — runs well, slowly, or does not fit. |
| **My AIs** | What each installed AI is good for, its limits, maker, licence, cost on this device, lighter and stronger versions; use a model file you already have. |
| **Create** | Pictures and video. |
| **Tools** | The agent, everyday tools, cameras, printers and other hardware, programs found, connections, bigger creative tools. |
| **Devices** | Link your own computers. |
| **Learn** | Lessons, glossary and checked outside material. |
| **Settings** | Language, look, privacy, the AI, voice, updates with "go back". |

Rules of the house: one main action per screen (the gold button); plain words, acronyms
spelled out; nothing is hidden because it is too demanding — the app says what will happen
and lets the person choose.

### Look

Colours of the Argentine flag. Sky blue and white carry the page; the sun's gold is kept for
the main action. The sun in the top bar shows what the AI is doing: rays for awake, turning
rays while it writes, a moon when it sleeps, a dashed circle when there is none.

| | Day | Night |
|---|---|---|
| Page | `#F3F8FD` | `#0B1626` |
| Surface | `#FFFFFF` | `#12233A` |
| Sky blue | `#74ACDF` | `#8DBDEA` |
| Text | `#0F2742` | `#EAF2FB` |
| Secondary text | `#4A5F7A` | `#9DB3CC` |
| Line | `#D5E3F1` | `#24405F` |
| Sun gold (main action) | `#F6B40E`, text `#3D1F05` | same |

Type: **Asap** for everything; **MuseoModerno** only for the name "Datas" (its capital G
reads like a Q, so it is not used for headings). Both are shipped with the app under the SIL
Open Font License. Look follows the device (Auto), or Day / Night in Settings.

### Files

`datas/server/ui/`: `index.html` (an empty frame), `app.css`, `i18n.js` (every word, English
and Spanish, as plain JSON), `app.js` (shared pieces: page building, server calls, dialogs,
jobs, safe Markdown), `chat.js`, `screens.js`; `agent.html`, `agent.css`, `agent.js` for the
agent's own window; `fonts/`.

- Sentences that come from the backend (why a camera could not be used, why a request was
  refused) are not in `i18n.js`: they are written once in English in the code and have their
  Spanish in `datas/words.py`; `tests/test_words.py` fails when one is missing.
- Pages are built from elements, never from HTML strings with user or AI text in them.
- The pages may run only their own script files (`script-src 'self'`).
- The window keeps nothing in the browser's own storage; state lives in the local service.

### Checking it

```bash
pytest tests/test_ui.py              # every text exists in both languages, no inline scripts, fonts shipped
python scripts/ui_shot.py out --all  # screenshots of every screen, wide and narrow (needs datas[qt])
python scripts/ui_shot.py out --lang es --js "go('learn')" --name learn-es
```

`ui_shot.py` prints anything the page writes to its console, so script errors show up.

## Everyday work: helpers, documents, saving answers

### Helpers

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

### Documents and pictures in a chat

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

### Saving an answer as a file

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

### Everyday tools (Tools screen)

| Tool | Does | Needs |
|---|---|---|
| Recording to text | a meeting, class, voice note or video becomes text with timestamps, plus a subtitles file (.srt) | voice installed; FFmpeg for formats other than WAV (Datas fetches a checked copy if none is found) |
| Text to audio | a text becomes a WAV file, and an MP3 when FFmpeg is available | voice installed |
| Long documents | summary or translation of a document of any length, piece by piece, then joined. With linked computers that have an AI ready, *Share the work with my linked devices* lets each take parts at the same time ([DEVICES.md](DEVICES.md#limits-stated-plainly)) | an AI running |

Code: [`datas/assistants/`](../datas/assistants), [`datas/docs.py`](../datas/docs.py),
[`datas/export.py`](../datas/export.py), [`datas/tools.py`](../datas/tools.py).
