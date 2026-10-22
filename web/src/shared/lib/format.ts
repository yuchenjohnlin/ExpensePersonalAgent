/** How money, days and times read on the page. The API sends money as strings ("4.68") and days as
 * "YYYY-MM-DD"; days are the ledger's own (no timezone), so they are never put through Date's UTC. */

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });

export function money(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  return usd.format(Number(value));
}

const WEEKDAYS = ["日", "一", "二", "三", "四", "五", "六"];

export function parseDay(day: string): Date {
  const [year, month, date] = day.split("-").map(Number);
  return new Date(year, month - 1, date);
}

export function dayText(day: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${day.getFullYear()}-${pad(day.getMonth() + 1)}-${pad(day.getDate())}`;
}

/** "10月9日 週四" */
export function dayLabel(day: string): string {
  const date = parseDay(day);
  return `${date.getMonth() + 1}月${date.getDate()}日 週${WEEKDAYS[date.getDay()]}`;
}

/** "10/9" */
export function shortDay(day: string): string {
  const date = parseDay(day);
  return `${date.getMonth() + 1}/${date.getDate()}`;
}

/** "2026年10月" for "2026-10" */
export function monthLabel(month: string): string {
  const [year, number] = month.split("-").map(Number);
  return `${year}年${number}月`;
}

export function shiftMonth(month: string, by: number): string {
  const [year, number] = month.split("-").map(Number);
  const moved = new Date(year, number - 1 + by, 1);
  return dayText(moved).slice(0, 7);
}

/** "剛剛", "5 分鐘前", "3 小時前", "2 天前", then the date. */
export function ago(moment: string, now: Date = new Date()): string {
  const seconds = Math.max(0, (now.getTime() - new Date(moment).getTime()) / 1000);
  if (seconds < 60) return "剛剛";
  if (seconds < 3600) return `${Math.floor(seconds / 60)} 分鐘前`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} 小時前`;
  if (seconds < 7 * 86400) return `${Math.floor(seconds / 86400)} 天前`;
  return shortDay(dayText(new Date(moment)));
}

/** A measure as typed: trailing zeros of the API's six decimals dropped ("2.850000" -> "2.85"). */
export function measure(value: string | null | undefined): string {
  if (value === null || value === undefined) return "";
  return value.includes(".") ? value.replace(/0+$/, "").replace(/\.$/, "") : value;
}
