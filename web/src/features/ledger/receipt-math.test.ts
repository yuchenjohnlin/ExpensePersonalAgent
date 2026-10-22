import { ApiError } from "@/shared/api/client";

import { percentText, resolveAdjustments, resolveLine, toCents } from "./receipt-math";

const line = (amount: string, discount = "", net = "") => resolveLine({ amount, discount, net });

test("money is read in cents, with or without a dollar sign", () => {
  expect(toCents("4.69")).toBe(469);
  expect(toCents("$ 12")).toBe(1200);
  expect(toCents("1.5")).toBe(150);
  expect(toCents("1.234")).toBeNull();
});

test("a line can be typed the ways receipts print it", () => {
  expect(line("11.25")).toEqual({ amount: "11.25", discount: null }); // just the price
  expect(line("11.25", "10%")).toEqual({ amount: "11.25", discount: "1.13" }); // a percentage off
  expect(line("", "2.00", "8.99")).toEqual({ amount: "10.99", discount: "2.00" }); // H Mart: paid and saved
  expect(line("", "20%", "8.00")).toEqual({ amount: "10.00", discount: "2.00" }); // paid and the percentage
  expect(line("", "", "3.50")).toEqual({ amount: "3.50", discount: "0.00" }); // only what was paid
});

test("a line that cannot add up says which cell is wrong", () => {
  const problem = (run: () => unknown) => {
    try {
      run();
    } catch (error) {
      return error instanceof ApiError ? error.fields : error;
    }
  };
  expect(problem(() => line("5.00", "", "6.00"))).toEqual({ net: ["折後價不能高於原價。"] });
  expect(problem(() => line("", "10%"))).toEqual({ discount: ["折扣用 % 時，請填原價或折後價。"] });
  expect(problem(() => line("5.00", "100%"))).toEqual({ discount: ["折扣要小於 100%。"] });
});

test("tip and whole-receipt discount may be a percentage of the subtotal before tax", () => {
  // 50 subtotal + 18% tip (9.00) + 4.00 tax = 63.00 paid
  expect(resolveAdjustments("63.00", { tax: "4.00", tip: "18%", receipt_discount: "" }))
    .toEqual({ tax: "4.00", tip: "9.00", receipt_discount: "0.00" });
  // blank tax stays unknown, not zero
  expect(resolveAdjustments("20.00", { tax: "", tip: "", receipt_discount: "1.00" }))
    .toEqual({ tax: null, tip: "0.00", receipt_discount: "1.00" });
  expect(percentText("0.030096")).toBe("3.01%");
  expect(percentText("0.18")).toBe("18%");
});
