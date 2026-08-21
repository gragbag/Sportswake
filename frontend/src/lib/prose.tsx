import type { ReactNode } from "react";

/**
 * Render generated body text as paragraphs and section headings.
 *
 * A deliberately tiny subset -- headings, paragraphs and inline emphasis,
 * nothing else -- built as React elements rather than through
 * dangerouslySetInnerHTML. The text is ours, not a feed's, but it still comes
 * out of a language model, and a model that decides to emit a <script> tag
 * should produce visible angle brackets rather than a script tag. No markdown
 * library either: pulling one in to render paragraphs would be a dependency
 * for a regex.
 *
 * Headings were not renderable at all until the brief started being composed
 * under them, which is the sort of gap that shows up as a literal "## Trades"
 * on the page rather than as an error.
 */

const HEADING = /^#{2,3}\s+/;

function inline(text: string, key: string): ReactNode[] {
  // Split on **bold** and *italic*, keeping the delimiters so they can be
  // turned into elements rather than stripped.
  const parts = text.split(/(\*\*[^*]+\*\*|\*[^*]+\*)/g);
  return parts.filter(Boolean).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      return <strong key={`${key}-${i}`}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*")) {
      return <em key={`${key}-${i}`}>{part.slice(1, -1)}</em>;
    }
    return <span key={`${key}-${i}`}>{part}</span>;
  });
}

/** Runs of whitespace inside a block are typesetting, not content. */
function flatten(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

export function Prose({ text }: { text: string }) {
  const blocks = text
    .split(/\n\s*\n/)
    .map((b) => b.trim())
    .filter(Boolean);

  const out: ReactNode[] = [];

  blocks.forEach((block, i) => {
    if (!HEADING.test(block)) {
      out.push(<p key={`p${i}`}>{inline(flatten(block), String(i))}</p>);
      return;
    }
    // A heading owns its first LINE only; anything after it in the same block
    // is the paragraph that follows. Collapsing whitespace before this check
    // would glue the two into one line of text.
    const brk = block.indexOf("\n");
    const head = (brk === -1 ? block : block.slice(0, brk)).replace(HEADING, "");
    const rest = brk === -1 ? "" : block.slice(brk).trim();

    out.push(<h2 key={`h${i}`}>{flatten(head)}</h2>);
    if (rest) out.push(<p key={`r${i}`}>{inline(flatten(rest), `r${i}`)}</p>);
  });

  return <>{out}</>;
}
