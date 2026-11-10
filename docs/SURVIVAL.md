# Offline survival

A place in Datas (*Offline survival* in the menu) for when the power, the water or the internet
fail — for a few hours, for weeks, or far from home — with the emphasis on getting through it
**together** with the people around you, not alone.

## What is there

- **Datas' own guides** (`datas/survival/guides.en.md`, `guides.es.md`), shipped with the
  program, so they are there from the first minute: the first hours, water, food, electricity,
  staying connected, health and first aid, outdoors, a crisis while travelling, living on your
  own means for a long time, doing it together, and using Datas with no internet. Every figure
  (boiling times, bleach drops, how long food keeps, generator distances) comes from the public
  source named at the end of its section; every section ends with what to do **together**.
- **A library to keep** (`datas/survival/catalog.json`): documents downloaded once from their own
  publishers — FEMA and Ready.gov (*Are You Ready?* / *¿Está listo?*, the CERT manual, the guide
  for older adults), CDC and CPSC (water, generators), WHO/WEDC (water and sanitation for a whole
  community), Hesperian (*Where There Is No Doctor* / *Donde no hay doctor* and *A Community Guide
  to Environmental Health* chapters), and public-domain books from
  Project Gutenberg (Kropotkin's *Mutual Aid*, camp-craft, *Walden*, *Robinson Crusoe*, Verne,
  *Don Quijote*, *Martín Fierro*). About 54 MB in all; each can be kept or removed on its own.
- **The survival helper** (*Ask*): a built-in helper that answers from the guides and every kept
  document (not the novels), names the document it used, gives no medicine doses and puts
  safety and the community first. It works with no internet and with the smallest AI.
- **Reading with no AI at all**: every guide opens in place; every document opens as a PDF or as
  plain text (plain text also works on a phone that opened a computer's Datas).

## How the library is kept honest

Nothing is offered until it was downloaded from its publisher and checked:
`scripts/check_survival.py` (run by `.github/workflows/library-sources.yml` whenever the list
changes and every Monday) downloads each document, prints what it really is (the title line of a
Gutenberg text, the first words of a PDF), and compares size and SHA-256 with the ones pinned in
the list. On a person's computer, a file that does not match is not kept and the screen says so,
with a link to the publisher's page. Licences are stated per document: US Government works are
public domain in the USA; Hesperian's Open Copyright allows non-profit copying; WHO keeps its
copyright and the file is fetched from the publisher for the person's own use; Project Gutenberg
texts are public domain in the USA (check your country's law).

## Not included, but recommended in the guides

- **Kiwix** (kiwix.org): an offline Wikipedia, WikiMed and Wikivoyage reader.
- **Meshtastic** (meshtastic.org): text messages over low-cost LoRa radios with no phone network.
- Map apps that save OpenStreetMap maps for offline use.

## What it is not

Not a replacement for local authorities, emergency services or a doctor. The guides say so at
the top, and the helper is told to say when to call for help.
