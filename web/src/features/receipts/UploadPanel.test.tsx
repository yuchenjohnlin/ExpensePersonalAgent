import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { fakeServer, renderApp } from "@/test/render";

import { UploadPanel } from "./UploadPanel";

beforeEach(() => {
  URL.createObjectURL = vi.fn(() => "blob:photo");
  URL.revokeObjectURL = vi.fn();
});

const photo = (name: string) => new File(["jpeg"], name, { type: "image/jpeg" });

async function pick(container: HTMLElement, names: string[]) {
  const input = container.querySelector<HTMLInputElement>("input[type=file][multiple]")!;
  await userEvent.upload(input, names.map(photo), { applyAccept: false });
}

test("photos become receipts as grouped, and are sent with those groups", async () => {
  const { sent } = fakeServer({ "POST /api/receipts": { status: 201, body: { receipts: [{ id: 1 }, { id: 2 }] } } });
  const { container } = renderApp(<UploadPanel />);
  await pick(container, ["kroger.jpg", "hmart-top.jpg", "hmart-bottom.jpg"]);
  expect(screen.getByText("3 張照片 → 3 張收據")).toBeInTheDocument();
  const joins = screen.getAllByRole("button", { name: /併到上一張/ });
  await userEvent.click(joins[1]); // the bottom half joins the top half
  expect(screen.getByText("3 張照片 → 2 張收據")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "上傳 2 張收據" }));
  await waitFor(() => expect(sent).toHaveLength(1));
  const form = sent[0].body as FormData;
  expect(form.getAll("photos").map((file) => (file as File).name)).toEqual(["kroger.jpg", "hmart-top.jpg", "hmart-bottom.jpg"]);
  expect(JSON.parse(form.get("groups") as string)).toEqual([[0], [1, 2]]);
  expect(form.get("allow_duplicates")).toBeNull();
  expect(await screen.findByText("拍收據，或選幾張照片")).toBeInTheDocument(); // cleared after the upload
});

test("photos already stored ask before being sent again", async () => {
  let calls = 0;
  const { sent } = fakeServer({
    "POST /api/receipts": () => (++calls === 1
      ? { status: 409, body: { error: "照片已經上傳過", duplicates: [{ index: 0, existing_photo_ids: [7], same_as_indices: [] }] } }
      : { status: 201, body: { receipts: [{ id: 3 }] } }),
  });
  const { container } = renderApp(<UploadPanel />);
  await pick(container, ["again.jpg"]);
  await userEvent.click(screen.getByRole("button", { name: "上傳 1 張收據" }));
  expect(await screen.findByText("有照片之前上傳過")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "仍要上傳" }));
  await waitFor(() => expect(sent).toHaveLength(2));
  expect((sent[1].body as FormData).get("allow_duplicates")).toBe("true");
});
