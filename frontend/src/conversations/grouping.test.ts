import { describe, expect, it } from "vitest";
import type { ConversationSummary } from "../api/types";
import { groupByRecency } from "./ConversationsContext";

const at = (id: string, updated: Date): ConversationSummary => ({
  id,
  title: id,
  created_at: updated.toISOString(),
  updated_at: updated.toISOString(),
});

describe("groupByRecency", () => {
  const now = new Date(2026, 10, 20, 15, 0); // 20 Nov 2026, 15:00 local
  const daysAgo = (days: number, hour = 12) => new Date(2026, 10, 20 - days, hour);

  it("buckets by local calendar day, keeping server order inside each group", () => {
    const groups = groupByRecency(
      [
        at("this-morning", daysAgo(0, 8)),
        at("yesterday", daysAgo(1)),
        at("last-week", daysAgo(5)),
        at("last-month", daysAgo(20)),
        at("old", daysAgo(90)),
        at("also-old", daysAgo(120)),
      ],
      now,
    );
    expect(groups.map((g) => [g.label, g.items.map((i) => i.id)])).toEqual([
      ["Today", ["this-morning"]],
      ["Yesterday", ["yesterday"]],
      ["Previous 7 days", ["last-week"]],
      ["Previous 30 days", ["last-month"]],
      ["Older", ["old", "also-old"]],
    ]);
  });

  it("omits empty groups", () => {
    expect(groupByRecency([at("a", daysAgo(0))], now).map((g) => g.label)).toEqual(["Today"]);
    expect(groupByRecency([], now)).toEqual([]);
  });
});
