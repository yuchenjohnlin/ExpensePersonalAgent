import { useSearchParams } from "react-router";

/** A receipt opens in a side sheet over whatever page you are on: the URL carries ?receipt=<id>,
 * so the back button closes it and a link can open it. */
export function useOpenReceipt() {
  const [, setParams] = useSearchParams();
  return (id: number | null) =>
    setParams((params) => {
      const next = new URLSearchParams(params);
      if (id === null) next.delete("receipt");
      else next.set("receipt", String(id));
      return next;
    });
}

export function useOpenedReceipt(): number | null {
  const [params] = useSearchParams();
  const value = Number(params.get("receipt"));
  return Number.isInteger(value) && value > 0 ? value : null;
}
