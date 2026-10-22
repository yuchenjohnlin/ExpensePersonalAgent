import { ago, dayLabel, measure, money, monthLabel, shiftMonth } from "./format";

test("money reads as dollars and unknown as a dash", () => {
  expect(money("4.68")).toBe("$4.68");
  expect(money("1234.5")).toBe("$1,234.50");
  expect(money(null)).toBe("—");
});

test("days are the ledger's own, never shifted by a timezone", () => {
  expect(dayLabel("2026-10-09")).toBe("10月9日 週五");
  expect(dayLabel("2026-01-01")).toBe("1月1日 週四");
  expect(monthLabel("2026-10")).toBe("2026年10月");
  expect(shiftMonth("2026-01", -1)).toBe("2025-12");
  expect(shiftMonth("2026-12", 1)).toBe("2027-01");
});

test("measures drop the API's trailing zeros", () => {
  expect(measure("2.850000")).toBe("2.85");
  expect(measure("12.000000")).toBe("12");
  expect(measure(null)).toBe("");
});

test("times read as how long ago", () => {
  const now = new Date("2026-10-22T12:00:00Z");
  expect(ago("2026-10-22T11:59:30Z", now)).toBe("剛剛");
  expect(ago("2026-10-22T11:55:00Z", now)).toBe("5 分鐘前");
  expect(ago("2026-10-21T12:00:00Z", now)).toBe("1 天前");
});
