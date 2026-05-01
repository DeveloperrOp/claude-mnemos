import type { ReactNode } from "react";

// Split a single paragraph string into ReactNode parts:
//  - `code` segments wrap in <code>
//  - **bold** segments wrap in <strong>
//  - Other text passes through as plain string
//
// Backticks parse first; the remaining text segments then get bold parsing.
// This means **bold inside code** stays literal text inside the <code>.
function renderInline(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  // Split on backtick groups (capturing).
  const codeParts = text.split(/(`[^`]+`)/g);
  codeParts.forEach((part, i) => {
    if (part.startsWith("`") && part.endsWith("`") && part.length >= 2) {
      out.push(
        <code
          key={`c${i}`}
          className="rounded bg-muted px-1.5 py-0.5 font-mono text-primary"
        >
          {part.slice(1, -1)}
        </code>,
      );
      return;
    }
    // Non-code part: split on **bold**.
    const boldParts = part.split(/(\*\*[^*]+\*\*)/g);
    boldParts.forEach((bp, j) => {
      if (bp.startsWith("**") && bp.endsWith("**") && bp.length >= 4) {
        out.push(
          <strong key={`b${i}-${j}`} className="font-semibold">
            {bp.slice(2, -2)}
          </strong>,
        );
      } else if (bp) {
        out.push(bp);
      }
    });
  });
  return out;
}

export function MultiPara({ value }: { value: string }) {
  // i18n string with \n\n paragraph separators → <p> per chunk.
  const paras = value.split(/\n\n+/).filter(Boolean);
  return (
    <div className="space-y-2">
      {paras.map((p, i) => (
        <p key={i} className="text-sm leading-relaxed whitespace-pre-line">
          {renderInline(p)}
        </p>
      ))}
    </div>
  );
}
