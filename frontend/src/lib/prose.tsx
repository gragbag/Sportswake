import type { ReactNode } from "react";

/**
 * Render generated body text as paragraphs.
 *
 * A deliberately tiny subset -- paragraphs and inline emphasis, nothing else
 * -- built as React elements rather than through dangerouslySetInnerHTML. The
 * text is ours, not a feed's, but it still comes out of a language model, and
 * a model that decides to emit a <script> tag should produce visible angle
 * brackets rather than a script tag. No markdown library either: pulling one
 * in to render paragraphs would be a dependency for a regex.
 */

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

export function Prose({ text }: { text: string }) {
  const paragraphs = text
    .split(/\n\s*\n/)
    .map((p) => p.replace(/\s+/g, " ").trim())
    .filter(Boolean);

  return (
    <>
      {paragraphs.map((p, i) => (
        <p key={i}>{inline(p, String(i))}</p>
      ))}
    </>
  );
}
