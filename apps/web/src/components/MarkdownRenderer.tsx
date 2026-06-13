import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "@/lib/utils";

/**
 * Props definition for the MarkdownRenderer component.
 */
interface MarkdownRendererProps {
  /** The raw markdown string to render. */
  content: string;
  /** Optional extra classes to style the container. */
  className?: string;
}

/**
 * A highly tailored, type-safe Markdown renderer component.
 * Specially configured with remark-gfm to support GFM tables, lists, and headings,
 * rendering custom React components mapped directly to the design system.
 *
 * @param {MarkdownRendererProps} props - Component properties.
 * @returns {React.JSX.Element} The rendered React elements.
 */
export function MarkdownRenderer({ content, className }: MarkdownRendererProps): React.JSX.Element {
  if (typeof content !== "string") {
    return <span className="text-destructive font-mono">Error: Invalid content type</span>;
  }

  return (
    <div className={cn("prose prose-sm dark:prose-invert max-w-none text-inherit leading-relaxed space-y-2.5", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          // Custom heading styles matching the UI theme
          h1: ({ ...props }) => <h1 className="text-base font-bold text-foreground mt-3 mb-1.5" {...props} />,
          h2: ({ ...props }) => <h2 className="text-sm font-bold text-foreground mt-2.5 mb-1.5" {...props} />,
          h3: ({ ...props }) => <h3 className="text-xs font-bold text-foreground/80 mt-2 mb-1" {...props} />,
          
          // Bold styling
          strong: ({ ...props }) => <strong className="font-bold text-primary dark:text-primary-light" {...props} />,
          
          // Block level elements
          p: ({ ...props }) => <p className="mb-2 last:mb-0" {...props} />,
          
          // Unordered & ordered lists
          ul: ({ ...props }) => <ul className="list-disc pl-5 mb-2.5 space-y-1" {...props} />,
          ol: ({ ...props }) => <ol className="list-decimal pl-5 mb-2.5 space-y-1" {...props} />,
          li: ({ ...props }) => <li className="text-xs" {...props} />,

          // GFM Tables styled to match the dark/light engineering grid theme
          table: ({ ...props }) => (
            <div className="my-3 overflow-x-auto rounded-lg border border-border/40 bg-card/30">
              <table className="min-w-full divide-y divide-border/30 text-xs text-left" {...props} />
            </div>
          ),
          thead: ({ ...props }) => <thead className="bg-muted/50 font-semibold text-foreground/80" {...props} />,
          tbody: ({ ...props }) => <tbody className="divide-y divide-border/20" {...props} />,
          tr: ({ ...props }) => <tr className="hover:bg-muted/10 transition-colors" {...props} />,
          th: ({ ...props }) => <th className="px-3 py-1.5 font-medium border-b border-border/30" {...props} />,
          td: ({ ...props }) => <td className="px-3 py-1.5 text-muted-foreground align-top" {...props} />,

          // Inline and block code formatting
          code: ({ className, children, ...props }) => {
            const match = /language-(\w+)/.exec(className || "");
            const inline = !match;
            return inline ? (
              <code className="bg-muted px-1.5 py-0.5 rounded text-[11px] font-mono text-foreground/90 border border-border/20" {...props}>
                {children}
              </code>
            ) : (
              <pre className="bg-muted/50 p-2.5 rounded-lg border border-border/20 overflow-x-auto text-[11px] font-mono my-2">
                <code {...props}>{children}</code>
              </pre>
            );
          },
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}
