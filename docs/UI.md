# The window

One window, a few screens, nothing loaded from outside the computer.

## Screens

| Screen | For |
|---|---|
| **Chat** (home) | Chats listed on the left with search; the top bar chooses the AI, a helper, and internet for this chat; answers can be stopped, copied, read aloud and saved as files. |
| **Add an AI** | What do you want to do, how much of the device may be used; a verdict for every AI — runs well, slowly, or does not fit. |
| **My AIs** | What each installed AI is good for, its limits, maker, licence, cost on this device, lighter and stronger versions; use a model file you already have. |
| **Create** | Pictures and video. |
| **Tools** | The agent, everyday tools, cameras, printers and other hardware, programs found, connections, bigger creative tools. |
| **Devices** | Link your own computers. |
| **Learn** | Lessons, glossary and checked outside material. |
| **Settings** | Language, look, privacy, the AI, paid services, voice, updates with "go back". |

Rules of the house: one main action per screen (the gold button); plain words, acronyms
spelled out; nothing is hidden because it is too demanding — the app says what will happen
and lets the person choose.

## Look

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

## Files

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

## Checking it

```bash
pytest tests/test_ui.py              # every text exists in both languages, no inline scripts, fonts shipped
python scripts/ui_shot.py out --all  # screenshots of every screen, wide and narrow (needs datas[qt])
python scripts/ui_shot.py out --lang es --js "go('learn')" --name learn-es
```

`ui_shot.py` prints anything the page writes to its console, so script errors show up.
