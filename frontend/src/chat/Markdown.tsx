import { memo } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CitationMarker } from "../sources/CitationMarker";
import { CITATION_HREF, remarkCitations } from "../sources/citations";

const components: Components = {
  a: ({ node: _node, href, ...props }) => {
    // "[Source N]" markers arrive here as links to "#source-N".
    const citation = href?.match(CITATION_HREF);
    if (citation) return <CitationMarker number={Number(citation[1])} />;
    // Other links in model output open away from the app, without referrer.
    return <a href={href} {...props} target="_blank" rel="noopener noreferrer" />;
  },
  // Wide tables scroll inside the message instead of widening the page.
  table: ({ node: _node, ...props }) => (
    <div className="answer-table">
      <table {...props} />
    </div>
  ),
};

const answerPlugins = [remarkGfm, remarkCitations];
const policyPlugins = [remarkGfm];

/**
 * Renders GitHub-flavoured Markdown. Raw HTML in the text is dropped
 * (skipHtml), so neither model output nor document text can inject markup.
 *
 * "answer": the copilot's words, sans, with [Source N] markers.
 * "policy": quoted policy text, set in the serif document voice.
 */
export const Markdown = memo(function Markdown({
  text,
  variant = "answer",
}: {
  text: string;
  variant?: "answer" | "policy";
}) {
  return (
    <div className={variant === "policy" ? "answer-prose policy-prose" : "answer-prose"}>
      <ReactMarkdown
        remarkPlugins={variant === "policy" ? policyPlugins : answerPlugins}
        components={components}
        skipHtml
      >
        {text}
      </ReactMarkdown>
    </div>
  );
});
