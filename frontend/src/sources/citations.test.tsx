import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import type { Citation } from "../api/types";
import { Markdown } from "../chat/Markdown";
import { CitationContext, citedNumbers, formatSection, partitionCitations } from "./citations";

const citation = (source: number, document = `Doc ${source}`): Citation => ({
  source,
  document,
  section: null,
  chunk_id: `chunk-${source}`,
  score: null,
});

describe("citedNumbers / partitionCitations", () => {
  it("finds only the exact [Source N] form the backend validates", () => {
    expect(citedNumbers("A [Source 1]. B [Source 3][Source 1]. C [source 2] [Source two]")).toEqual(
      new Set([1, 3]),
    );
  });

  it("separates cited sources from sources only given as context", () => {
    const all = [citation(1), citation(2), citation(3)];
    const { cited, reviewed } = partitionCitations("Yes [Source 2].", all);
    expect(cited.map((c) => c.source)).toEqual([2]);
    expect(reviewed.map((c) => c.source)).toEqual([1, 3]);
  });
});

describe("formatSection", () => {
  it("drops a leading segment that repeats the document title", () => {
    expect(formatSection("Leave Policy > Annual leave > Carry-over", "Leave Policy")).toBe(
      "Annual leave › Carry-over",
    );
    expect(formatSection("leave policy > Scope", "Leave Policy")).toBe("Scope");
  });

  it("hides a path that only repeats the title, keeps one that doesn't start with it", () => {
    expect(formatSection("Leave Policy", "Leave Policy")).toBeNull();
    expect(formatSection("Scope > Eligibility", "Leave Policy")).toBe("Scope › Eligibility");
    expect(formatSection(null)).toBeNull();
  });
});

describe("Markdown citation rendering", () => {
  const render = (text: string, citations: Citation[] | null) =>
    renderToStaticMarkup(
      <CitationContext.Provider value={{ citations, activeSource: null, open: () => {} }}>
        <Markdown text={text} />
      </CitationContext.Provider>,
    );

  it("turns markers into citation buttons when citations are known", () => {
    const html = render("Leave is 24 days [Source 1].", [citation(1, "Leave Policy")]);
    expect(html).toContain('<button type="button" class="cite"');
    expect(html).toContain('aria-label="Source 1: Leave Policy"');
    expect(html).not.toContain("[Source 1]");
  });

  it("renders markers inert while citations are unknown (streaming)", () => {
    const html = render("Leave is 24 days [Source 1].", null);
    expect(html).toContain('class="cite cite-inert"');
    expect(html).not.toContain("<button");
  });

  it("leaves markers inside code untouched", () => {
    const html = render("Use `[Source 9]` literally.", [citation(9)]);
    expect(html).toContain("<code>[Source 9]</code>");
  });

  it("drops raw HTML from model output", () => {
    const html = render('Hi <img src=x onerror="alert(1)"> [Source 1]', [citation(1)]);
    expect(html).not.toContain("<img");
    expect(html).not.toContain("onerror");
  });
});
