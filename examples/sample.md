# Quarterly engineering report

This sample document exists so you can see the template options at work: tables, code blocks,
quotes, footnotes and a generated table of contents.

## At a glance

| Area | Status | Owner |
| --- | --- | --- |
| Rendering pipeline | Done | Platform |
| Template editor | Done | Platform |
| Accessibility review | In progress | Design |
| Archival storage | Planned | Infrastructure |

## How the pipeline works

Markdown is converted to HTML first, then WeasyPrint turns that HTML into a paginated PDF.

```python
from md2pdf import converter, templates

template = templates.default_template()
result = converter.convert("# Title\n\nBody.", template, doc_id="DOC-0001")
print(result.page_count, result.output_name)
```

Inline code such as `converter.convert()` shares the monospace styling, and long code lines wrap
instead of running off the page.

### Page numbers

Footers use `{page}` and `{pages}` tokens, so the same template works for one page or a hundred.

> Templates are data, not code. Everything the UI exposes can be stored in a project folder and
> reviewed in a pull request.

## Decisions

1. Keep the template model in JSON so projects stay portable.
2. Store generated PDFs next to the Markdown they came from.
3. Never reuse a document id inside a project.

!!! note "Admonitions"
    Block quotes, admonitions and tables all pick up the accent color from the theme.

Term
: Definition lists are supported as well.

[^1]: Footnotes render at the end of the document with a back link.

## Next steps

- Add a cover page from the Cover tab.
- Turn on **Number h2/h3 headings** for numbered sections.
- Export the template and hand it to a colleague.

\newpage

## Page breaks on demand

That line above this heading starts a new page: it is a plain `\newpage` marker, the same one the
**Page breaks** panel inserts for you. Use one above a table or a section that should not be split
across two pages, and the live preview draws a dashed line where the page will end.
