import { groupsFrom } from "./grouping";
import { dateDoubt, summarizeReasons } from "./status";

test("photos join the previous photo's receipt only when marked", () => {
  expect(groupsFrom([false, false, false])).toEqual([[0], [1], [2]]);
  expect(groupsFrom([false, false, true])).toEqual([[0], [1, 2]]); // two halves of one long receipt
  expect(groupsFrom([true, true])).toEqual([[0, 1]]); // the first photo has no previous to join
});

test("per-item check failures fold into one line", () => {
  const item = (n: number) => `第 ${n} 項的數量或淨重乘單價與該行金額不一致，請核對計價方式。`;
  const total = "小計加稅與小費、減整張折扣，與總額不一致；未自動修改任何讀取值。";
  expect(summarizeReasons([total, item(1)])).toEqual([total, item(1)]);
  expect(summarizeReasons([total, ...[1, 2, 3, 5, 6, 7, 8].map(item)])).toEqual([
    total, "7 個品項的數量（或重量）乘單價對不上金額（第 1、2、3、5、6、7 等 項），請核對計價方式。"]);
});

test("a read date far before the upload, or after it, is doubted", () => {
  const uploaded = "2026-10-22T04:00:00Z";
  expect(dateDoubt("2026-10-20", uploaded)).toBeNull();
  expect(dateDoubt("2023-09-19", uploaded)).toMatch(/^讀到的日期比上傳早了 \d+ 天/); // "09/19/26" read as 2023
  expect(dateDoubt("2026-11-01", uploaded)).toBe("讀到的日期在上傳之後，可能讀錯了。");
  expect(dateDoubt(null, uploaded)).toBeNull();
});
