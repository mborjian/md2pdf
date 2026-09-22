# md2pdf

Markdown to PDF with templates, project folders and a Streamlit UI. Markdown becomes HTML with
[python-markdown](https://python-markdown.github.io/), and WeasyPrint turns that HTML into a
paginated, stylesheet-driven PDF.

## Features

- Streamlit UI with two modes: a **one-time convert** and a **project workspace**
- Paste Markdown, drag and drop files, load the bundled example, or reopen a document you converted earlier
- Templates stored as JSON: page size and margins, fonts and colours, tables, code highlighting,
  header and footer, cover page, watermark, table of contents, custom CSS
- Header and footer margin boxes with logos, running chapter names and page numbers (`1 / 7`, roman, alpha)
- Syntax-highlighted code blocks (Pygments themes), styled tables that repeat their header row on every page
- Document ids from a pattern: sequential, per year or month, random, UUID, timestamp, alphabetic, or any mix
- Projects keep templates, uploaded assets, Markdown copies, PDFs and a conversion history in one folder
- Both a CLI and the UI share the same engine

## Install

WeasyPrint needs Pango from the system, so install that first:

```bash
brew install pango libffi          # macOS
apt install libpango-1.0-0 libpangoft2-1.0-0 libffi-dev   # Debian / Ubuntu
```

Then the package itself:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Python 3.10 or newer is required: the inline PDF viewer is built on a recent Streamlit, and
Streamlit 1.50 is the last release that supports 3.9. The suite is developed and verified on 3.12.

## Streamlit app

```bash
md2pdf ui                                  # or: streamlit run app.py
streamlit run src/md2pdf/streamlit_app.py   # the packaged entry point, no console script needed
```

The app opens on `http://localhost:8501`. On macOS `md2pdf ui` is the recommended entry point: it
puts Homebrew's `lib` on the dynamic loader path before starting Python, so WeasyPrint finds Pango.

### One-time convert

1. Pick a source: paste Markdown, drop one or more `.md` files, load the example, or convert a
   document that already lives in an open project.
2. Optionally tick **Save copy** and choose a folder — type it or press **Browse…** for the system
   folder dialog. Without it, nothing is written to disk and the result is only offered as a download.
3. Press **Convert to PDF**. The Preview panel then shows the rendered PDF next to the live HTML
   view, so a template change can be judged in one click: convert again and the two panes update
   together. The layout selector switches between **PDF and preview**, **PDF only** and **Preview
   only**, and the PDF is also offered as a download.

### Project workspace

A project is just a folder. Create one from the Projects tab, or open any folder that already
contains a `project.json`, wherever it lives on disk.

```
Reports/
  project.json      name, description, schema version
  templates/        one JSON file per template
  documents/        Markdown copy of everything converted
  output/           generated PDFs
  assets/           logos, images, any file a template refers to
  manifest.json     history: doc id, title, template, pages, file names, timestamps
  state.json        document id counters
  session.json      where you left off: template, Markdown, source mode, layout
```

Everything stays inside that folder, so a project can be moved, copied, archived, or committed to
git. The Library tab lists the history and can send an old Markdown file back into the editor with
its document id intact.

**Opening a project.** Type a path, pick one from the list of projects the app has seen, or press
**Browse…** for the system folder dialog, the same panel your file manager shows. Picking a folder
*inside* a project (its `output/`, say) opens the project it belongs to, and the next dialog starts
beside the last project you used. The dialog is Tk, launched in its own process so it can be raised
from a browser session; a Python without tkinter gets a clear message instead of a failure.

**Continue where you left off.** Every run stores the template you were editing — colors, fonts,
logos, all of it — together with the Markdown, the source mode and the preview layout in the
project's `session.json`. Reopening the project puts them all back, and the sequence counter in
`state.json` carries on from the last id. Editing a template file by hand (or with the CLI) wins over
the stored session, so the files on disk stay the source of truth.

### Templates

Presets: **Modern brief**, **Classic report**, **Code handbook**, **Minimal letter**, **Manual with
cover**. Every setting is editable in the Template tab, saved into the project, exported as JSON, or
imported from a JSON file someone sent you.

What the editor covers:

| Group | Settings |
| --- | --- |
| Page | A4/A3/A5/A6/B5/Letter/Legal/Tabloid/Executive/custom, portrait or landscape, four margins |
| Typography | Body, heading and monospace font stacks, sizes, line height, heading scale, text, heading, muted, border and accent colours |
| Tables & code | Header colour, zebra stripes, borders, full width, table font size, Pygments theme, code background and size |
| Header & footer | Enable per side, text with tokens, alignment, logo from project assets, logo size, font size, colour, rule, visibility on the first page |
| Cover | Title, subtitle, author, company, logo, background colour or image, accent bar, date, document id, vertical alignment |
| Watermark | Text, colour, size, opacity, rotation |
| Markdown | TOC and its depth, numbered h2/h3, tables, fenced code, syntax highlighting, line numbers, footnotes, admonitions, smart quotes, page breaks before h1/h2 |
| Document ID | Pattern, uniqueness, where the id appears (header, footer, cover, file name, PDF metadata) |
| Metadata & advanced | Title, author, subject, keywords, language, first page number, page number style, hyphenation, justification, printed link URLs, custom CSS appended last |

### Header, footer and file name tokens

`{title}` `{subtitle}` `{author}` `{company}` `{project}` `{template}` `{filename}` `{stem}`
`{version}` `{doc_id}` `{date}` `{time}` `{datetime}` `{page}` `{pages}` `{chapter}` `{section}`

- `{page}` and `{pages}` become real PDF page numbers, `{chapter}` and `{section}` follow the running
  h1 and h2 while the document prints.
- Optional parts go in brackets and disappear when a token inside them is empty:

  ```
  [{doc_id}  ·  ]Page {page} of {pages}     →  DOC-0007  ·  Page 3 of 12
                                            →  Page 3 of 12            (no id)
  ```

### Document ids

Patterns are free-form; the app shows the next value before you convert. Presets include:

| Preset | Pattern | Example |
| --- | --- | --- |
| Sequential | `DOC-{seq:5}` | `DOC-00042` |
| Year + sequence | `{year}-{seq:4}` | `2026-0007` |
| Month + sequence | `{date:%Y%m}-{seq:3}` | `202609-014` |
| Random | `DOC-{rand:8}` | `DOC-K7F3M9QP` |
| Random hex | `{randhex:10}` | `9f2c4a7b13` |
| UUID | `{uuid}` | `3f1a…` |
| Timestamp | `DOC-{timestamp:%Y%m%dT%H%M%S}` | `DOC-20260922T131415` |
| Title slug + sequence | `{slug}-{seq:3}` | `release-notes-004` |
| Project prefix + sequence | `{project:ACME}-{year}-{seq:3}` | `ACME-2026-015` |
| Alphabetic counter | `DOC-{letter}` | `DOC-AK` |

`{seq}`, `{letter}` and `{roman}` consume the project counter in `state.json`, so ids never repeat;
every other token is derived. With **Never reuse an id inside a project** on, the counter keeps
moving until the id is new. Outside a project the CLI stores its counter in `.md2pdf-state.json`
next to the output, and the app keeps counters in memory for the session.

## Command line

```bash
md2pdf notes.md                                  # writes notes.pdf next to the source
md2pdf notes.md -o out/                          # into a folder
md2pdf notes.md --template "Classic report"      # a preset
md2pdf notes.md --template invoice.json          # a template file
md2pdf notes.md --project ~/Documents/md2pdf-projects/Reports   # uses project templates, ids, history
md2pdf notes.md --page-size A5 --landscape --toc --doc-id "INV-{seq:4}"
md2pdf notes.md --save-html debug.html --save-css debug.css     # inspect the intermediate output

md2pdf project init Reports --preset "Manual with cover"
md2pdf project list
md2pdf templates --project Reports               # presets, project templates, token reference
md2pdf ui --port 8600
python -m md2pdf notes.md                        # same thing without the console script
```

`md2pdf` without a subcommand treats the first argument as the input file, so `md2pdf report.md`
just works.

## Styling notes

- Page geometry comes from `@page` rules: named pages give the cover its own margins, and margin
  boxes (`@top-left` … `@bottom-right`) hold headers and footers with `counter(page)`,
  `counter(pages)`, `string(chapter)` and `string(section)`.
- Code blocks use `.codehilite` CSS generated by Pygments, so any installed theme name works.
- Tables use `display: table-header-group` on `thead`, which repeats the header row across pages,
  and `break-inside: avoid` on rows so a row never splits in half.
- The table of contents links to heading anchors and its entries show PDF page numbers through
  `target-counter()`.
- Any font stack only works if that font is installed on the machine that renders the PDF.
- Headers, footers, page numbers and running headings exist in the PDF only; the in-app preview
  approximates them with labelled bars above and below the text column.

## Development

```bash
pytest
```

The suite runs without WeasyPrint or Streamlit: the pipeline tests skip themselves when a dependency
is missing, while the template model, stylesheet builder, document id engine, project store and CLI
tests run everywhere. `tests/test_ui.py` drives the real Streamlit app headlessly through Streamlit's
`AppTest` harness, so widget keys, session state and the conversion flow are covered without a
browser.

```
src/md2pdf/cli.py        command line entry point
src/md2pdf/converter.py  Markdown -> HTML -> PDF
src/md2pdf/native_env.py Homebrew library path helper for WeasyPrint on macOS
src/md2pdf/docids.py     document id patterns and counters
src/md2pdf/projects.py   project folders, assets, history
src/md2pdf/styles.py     CSS generation
src/md2pdf/templates.py  template model, presets, JSON
src/md2pdf/ui.py         Streamlit app
examples/sample.md       sample document used by the app
```
