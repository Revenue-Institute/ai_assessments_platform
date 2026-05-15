import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

interface Props {
  source: string;
  className?: string;
}

// Renders an assessment question prompt as GFM-flavored markdown. Code
// fences land in a styled <pre><code> block with monospace + horizontal
// scroll; inline code uses a subtle background chip; lists and headings
// inherit the surrounding type scale.
export function PromptMarkdown({ source, className }: Props) {
  return (
    <div
      className={[
        "prompt-markdown space-y-3 text-pretty text-sm leading-relaxed",
        className ?? "",
      ]
        .join(" ")
        .trim()}
    >
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          h1: ({ children }) => (
            <h2 className="font-semibold text-lg">{children}</h2>
          ),
          h2: ({ children }) => (
            <h3 className="font-semibold text-base">{children}</h3>
          ),
          h3: ({ children }) => (
            <h4 className="font-semibold text-sm uppercase tracking-wide">
              {children}
            </h4>
          ),
          p: ({ children }) => (
            <p className="text-foreground">{children}</p>
          ),
          ul: ({ children }) => (
            <ul className="list-disc space-y-1 pl-6">{children}</ul>
          ),
          ol: ({ children }) => (
            <ol className="list-decimal space-y-1 pl-6">{children}</ol>
          ),
          li: ({ children }) => (
            <li className="text-foreground">{children}</li>
          ),
          a: ({ children, href }) => (
            <a
              className="text-primary underline-offset-4 hover:underline"
              href={href}
              rel="noopener noreferrer"
              target="_blank"
            >
              {children}
            </a>
          ),
          blockquote: ({ children }) => (
            <blockquote className="border-border border-l-2 pl-4 text-muted-foreground italic">
              {children}
            </blockquote>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table className="w-full border-collapse text-sm">
                {children}
              </table>
            </div>
          ),
          th: ({ children }) => (
            <th className="border-border border-b px-2 py-1 text-left font-semibold">
              {children}
            </th>
          ),
          td: ({ children }) => (
            <td className="border-border border-b px-2 py-1">{children}</td>
          ),
          code: ({ className: cn, children, ...rest }) => {
            const isBlock = cn?.startsWith("language-");
            if (isBlock) {
              return (
                <code className={cn} {...rest}>
                  {children}
                </code>
              );
            }
            return (
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[0.92em]">
                {children}
              </code>
            );
          },
          pre: ({ children }) => (
            <pre className="overflow-x-auto rounded-md border border-border bg-muted/40 p-3 font-mono text-xs leading-snug">
              {children}
            </pre>
          ),
        }}
      >
        {source}
      </ReactMarkdown>
    </div>
  );
}
