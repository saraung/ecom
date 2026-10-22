// src/pages/McpAgent/Markdown.jsx
import React from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

// Assistant reply renderer: full Markdown (bold, lists, headings, code,
// GFM tables) styled to the admin theme. react-markdown escapes raw HTML
// by default, so replies cannot inject markup.
const components = {
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-[13px] border-collapse">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted">{children}</thead>,
  th: ({ children }) => (
    <th className="px-2.5 py-1.5 text-left font-semibold border-b border-border whitespace-nowrap">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-2.5 py-1.5 border-b border-border last:border-b-0 align-top break-words">
      {children}
    </td>
  ),
  code: ({ className, children }) =>
    className ? (
      <code className={className}>{children}</code>
    ) : (
      <code className="px-1 py-0.5 rounded bg-foreground/10 font-mono text-[13px]">
        {children}
      </code>
    ),
  pre: ({ children }) => (
    <pre className="my-1.5 p-2.5 rounded-lg bg-foreground/10 font-mono text-[13px] overflow-x-auto whitespace-pre-wrap break-words">
      {children}
    </pre>
  ),
  ul: ({ children }) => <ul className="my-1.5 pl-5 space-y-0.5 list-disc">{children}</ul>,
  ol: ({ children }) => <ol className="my-1.5 pl-5 space-y-0.5 list-decimal">{children}</ol>,
  p: ({ children }) => <p className="my-1 first:mt-0 last:mb-0">{children}</p>,
  // Defense-in-depth: the agent is instructed never to paste image URLs
  // itself (cards render from backend data), but if one slips through,
  // keep it small, rounded, and non-referring instead of full-bleed.
  img: ({ src, alt }) => (
    <img
      src={src}
      alt={alt || 'Attached image'}
      loading="lazy"
      referrerPolicy="no-referrer"
      className="my-2 max-h-48 w-auto max-w-full rounded-lg border border-border object-cover"
    />
  ),
  h1: ({ children }) => <h1 className="text-base font-bold mt-2 mb-1">{children}</h1>,
  h2: ({ children }) => <h2 className="text-[15px] font-bold mt-2 mb-1">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-semibold mt-2 mb-1">{children}</h3>,
};

const AssistantMarkdown = ({ text }) => {
  // Safety net for model verbosity: collapse 3+ newlines to a paragraph
  // break so airy replies (and old stored threads) render tight. The
  // system prompt mandates compact lists; this covers any drift.
  const compact = String(text ?? '').replace(/\n{3,}/g, '\n\n');
  return (
    <div className="min-w-0 text-sm break-words">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {compact}
      </ReactMarkdown>
    </div>
  );
};

export default AssistantMarkdown;
