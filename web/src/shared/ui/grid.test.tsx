import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ApiError } from "@/shared/api/client";

import { GridCell, RowError, RowState, useGridRow, useReportRisk, useRiskRegistry } from "./grid";

type Row = { name: string; amount: string };
type Save = (next: Row, changed: Partial<Row>) => Promise<Row | void>;

function Table({ save, create = false, report }: {
  save: Save; create?: boolean; report?: (key: string, atRisk: boolean) => void;
}) {
  const row = useGridRow<Row>(create ? { name: "", amount: "" } : { name: "Milk", amount: "3.00" }, save, { create });
  useReportRisk(report ?? (() => {}), "row", row.atRisk);
  return (
    <table>
      <tbody>
        <tr>
          {(["name", "amount"] as const).map((key) => (
            <td key={key}>
              <GridCell row={row} keys={[key]}>
                <input aria-label={key} value={row.value[key]} onChange={(event) => row.set(key, event.target.value)} />
              </GridCell>
            </td>
          ))}
          <td><RowState row={row} name="row" /></td>
        </tr>
        <RowError row={row} labels={{ amount: "金額" }} colSpan={3} />
      </tbody>
      <tfoot><tr><td><button type="button">outside</button></td></tr></tfoot>
    </table>
  );
}

test("a saved row saves only the changed field when you leave the cell", async () => {
  const save = vi.fn<Save>(async (next) => next);
  render(<Table save={save} />);
  await userEvent.clear(screen.getByLabelText("amount"));
  await userEvent.type(screen.getByLabelText("amount"), "3.50");
  expect(save).not.toHaveBeenCalled(); // no timer: typing alone saves nothing
  await userEvent.click(screen.getByText("outside"));
  await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
  expect(save.mock.calls[0][1]).toEqual({ amount: "3.50" });
  expect(await screen.findByText("已存")).toBeInTheDocument();
});

test("moving between cells of the same row saves; Esc puts the cell back without saving", async () => {
  const save = vi.fn<Save>(async (next) => next);
  render(<Table save={save} />);
  await userEvent.type(screen.getByLabelText("name"), " 2%");
  await userEvent.keyboard("{Escape}");
  expect(screen.getByLabelText("name")).toHaveValue("Milk");
  await userEvent.click(screen.getByText("outside"));
  expect(save).not.toHaveBeenCalled(); // nothing left to save
});

test("a failed save keeps the edit, says why, and is not resent until changed or Enter", async () => {
  const save = vi.fn<Save>(async () => {
    throw new ApiError(400, { error: "請檢查輸入內容。", fields: { amount: ["請填金額。"] } });
  });
  const report = vi.fn();
  render(<Table save={save} report={report} />);
  await userEvent.type(screen.getByLabelText("amount"), "x");
  await userEvent.click(screen.getByText("outside"));
  expect(await screen.findByRole("alert")).toHaveTextContent("請檢查輸入內容。 金額：請填金額。");
  expect(screen.getByLabelText("amount")).toHaveValue("3.00x");
  expect(screen.getByText("未存")).toBeInTheDocument();
  expect(report).toHaveBeenLastCalledWith("row", true); // the page will ask before throwing it away

  await userEvent.click(screen.getByLabelText("amount"));
  await userEvent.click(screen.getByText("outside"));
  expect(save).toHaveBeenCalledTimes(1); // same edit, just passing through: not resent

  await userEvent.click(screen.getByLabelText("amount"));
  await userEvent.keyboard("{Enter}");
  await waitFor(() => expect(save).toHaveBeenCalledTimes(2)); // Enter tries again
});

test("one request per row: what is typed during a save is sent after it", async () => {
  let finish: (row: Row) => void = () => {};
  let calls = 0;
  const save = vi.fn<Save>((next) => (++calls === 1
    ? new Promise<Row>((resolve) => { finish = resolve; })
    : Promise.resolve(next)));
  render(<Table save={save} />);
  await userEvent.type(screen.getByLabelText("name"), "!");
  await userEvent.click(screen.getByLabelText("amount")); // leaves the name cell: first save starts
  await userEvent.type(screen.getByLabelText("amount"), "9");
  await userEvent.click(screen.getByText("outside")); // second leave while the first is on its way
  expect(save).toHaveBeenCalledTimes(1);
  finish({ name: "Milk!", amount: "3.00" });
  await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
  expect(save.mock.calls[1][1]).toEqual({ amount: "3.009" });
});

test("the new row saves nothing on leaving; Enter creates it and empties the row", async () => {
  const save = vi.fn<Save>(async () => {});
  const report = vi.fn();
  render(<Table save={save} create report={report} />);
  await userEvent.type(screen.getByLabelText("name"), "Bread");
  await userEvent.click(screen.getByText("outside"));
  expect(save).not.toHaveBeenCalled();
  expect(report).toHaveBeenLastCalledWith("row", true); // half-typed: would be lost
  expect(screen.getByRole("button", { name: "新增 row" })).toBeInTheDocument();

  await userEvent.click(screen.getByLabelText("name"));
  await userEvent.keyboard("{Enter}");
  await waitFor(() => expect(save).toHaveBeenCalledWith({ name: "Bread", amount: "" }, { name: "Bread" }));
  await waitFor(() => expect(screen.getByLabelText("name")).toHaveValue(""));
  expect(report).toHaveBeenLastCalledWith("row", false);
});

test("the registry asks only when a row it covers would lose something", () => {
  let registry: ReturnType<typeof useRiskRegistry> | null = null;
  function Page() {
    registry = useRiskRegistry();
    return null;
  }
  render(<Page />);
  const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
  expect(registry!.confirmLeave()).toBe(true);
  registry!.report("7:new", true);
  expect(registry!.confirmLeave("8:")).toBe(true); // another expense's lines: no question
  expect(registry!.confirmLeave("7:")).toBe(false);
  expect(registry!.confirmLeave()).toBe(false);
  expect(confirm).toHaveBeenCalledTimes(2);
  confirm.mockRestore();
});
