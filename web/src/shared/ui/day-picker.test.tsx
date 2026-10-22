import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";

import { DayPicker, monthCells, useDayPicker, weekCells } from "./day-picker";

test("a week runs Sunday to Saturday; a month fills whole weeks", () => {
  expect(weekCells("2026-10-22")).toEqual([
    "2026-10-18", "2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23", "2026-10-24"]);
  expect(weekCells("2026-11-01")[0]).toBe("2026-11-01"); // a Sunday starts its own week
  const october = monthCells("2026-10");
  expect(october).toHaveLength(35);
  expect(october[0]).toBe("2026-09-27");
  expect(october.at(-1)).toBe("2026-10-31");
});

function Picker({ onSelect }: { onSelect?: (day: string) => void }) {
  const [day, setDay] = useState("2026-10-22");
  const picker = useDayPicker(day);
  return (
    <DayPicker picker={picker} selected={day} today="2026-10-22" label="選擇日期" summary="本週 $0.00"
      onSelect={(next) => { onSelect?.(next); setDay(next); }}
      describe={() => "無支出"} cell={() => null} />
  );
}

const pressed = () => screen.getAllByRole("button", { pressed: true }).map((button) => button.getAttribute("aria-label") ?? button.textContent);

test("arrows move the week on screen, not the chosen day; 今天 chooses today", async () => {
  const onSelect = vi.fn();
  render(<Picker onSelect={onSelect} />);
  expect(screen.getByText("10月18日 – 10月24日")).toBeInTheDocument();
  expect(pressed()).toEqual(["週", "2026-10-22，無支出"]);

  await userEvent.click(screen.getByRole("button", { name: "下一週" }));
  expect(screen.getByText("10月25日 – 10月31日")).toBeInTheDocument();
  expect(pressed()).toEqual(["週"]); // the 22nd is still chosen, just not on screen
  expect(onSelect).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: "今天" }));
  expect(onSelect).toHaveBeenCalledWith("2026-10-22");
});

test("月 opens the month; a grey day of the next month brings that month; 週 goes back to the chosen week", async () => {
  render(<Picker />);
  await userEvent.click(screen.getByRole("button", { name: "月" }));
  expect(screen.getByLabelText("選擇月份")).toHaveValue("2026-10");
  expect(screen.getByRole("button", { name: "2026-09-27，非本月" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "下一個月" }));
  expect(screen.getByLabelText("選擇月份")).toHaveValue("2026-11");
  await userEvent.click(screen.getByRole("button", { name: "2026-12-01，非本月" }));
  expect(screen.getByLabelText("選擇月份")).toHaveValue("2026-12");
  expect(pressed()).toContain("2026-12-01，無支出");

  await userEvent.click(screen.getByRole("button", { name: "週" }));
  expect(screen.getByText("11月29日 – 12月5日")).toBeInTheDocument();
});
