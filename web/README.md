# web/: the page for the rebuilt app

React 19, TypeScript and Vite, talking to `server/` (rebuild-web-frontend). Server data goes through TanStack Query; styling is Tailwind with shadcn/ui-style components kept in this repo. The old `frontend/` stays untouched until it retires.

## Running it

```bash
server/dev.sh cli createuser yuchen
```

```bash
server/dev.sh run
```

```bash
cd web && npm install && npm run dev
```

Then open `http://localhost:5173`. Vite passes `/api` to the server on `127.0.0.1:8000`, so the page and the API share one origin and the session cookie just works. `npm test` runs the tests (Vitest, jsdom), `npm run typecheck` the types, `npm run build` both plus a production build in `dist/`.

Deployed, `web/Dockerfile` builds `dist/` and serves it with nginx (`web/nginx.conf`), which also passes `/api/` to the API container, so the page and the API are one origin there too; see `deploy/README.md`.

## The screens

- **收件匣 (inbox, the home page):** only what needs you. Receipts that could not post themselves, with why. Expenses that did, beside their photo: fix the date or the category in place, then 看過了. A read date the model itself doubted, or that is far from the upload day, is called out here, because the server's checks cannot catch a wrong date (auto-post-wrong-date).
- **收據 (receipts):** take or pick photos, mark which photos are one receipt ("併到上一張"), upload; watch each go 讀取中 → 已入帳 or 要看一下.
- **支出 (calendar):** the chosen day is a table you keep typing into (calendar-day-is-the-entry-table). Above it, the week (each day's total and up to two shops); 月 opens the month (date and amount), ‹ › move what is on screen without changing the day, 今天 goes back. Below, one row per expense: click a cell and change it, leaving the cell saves. The last row is new: type it, Enter adds it on that day, and the cursor waits in the next new row. ▸ opens an expense's lines, edited the same way, with its tax, tip and receipt discount under them.
- **A receipt** opens in a side sheet over whatever page is open (`?receipt=<id>` in the URL): its photos beside what was read, the reasons it was set aside, and posting it by hand, reading it again, or unposting.

On a wide screen the menu is a sidebar; on a phone it is a bottom bar with the camera in the middle.

## How the code is layered

```
src/
  app/        wiring: providers, routes, the frame (sidebar / bottom bar)       imports pages, features, shared
  pages/      one per route, putting features together                          imports features, shared
  features/   auth, ledger, receipts: one per server module                     imports shared (+ see below)
    <name>/api.ts      the only code that calls that module's endpoints
    <name>/index.ts    what other code may use from the feature
  shared/     knows nothing about expenses or receipts                          imports nothing above
    api/client.ts      the only fetch: CSRF header, JSON, ApiError
    ui/                buttons, inputs, dialogs, sheet, tabs, badges...
                       grid.tsx: tables edited in place; day-picker.tsx: the week / month strip
    lib/               formatting money and days, cn()
```

The rule is the same as the server's: an arrow only points down. A feature may use another feature only where its server module depends on that module (receipts uses the ledger, never the other way). So when a page needs both, like the calendar showing each expense's receipt photo, the page combines them; the ledger's `ExpenseTable` just has an `aside` slot for it. Other code imports a feature through its `index.ts`, never its files.

Why bother: each piece has one job and one place. A change to how the server answers expenses touches `features/ledger/api.ts` and the components that show them; a new look for every button touches `shared/ui/button.tsx`; nothing else moves.

**Components and hooks.** A component draws something; a hook holds logic and data a component uses. `shared/ui` components only draw (they take props and know no API). Feature components use their feature's hooks (`useDay`, `useUpdateExpense`) and `shared/ui`. Pages mostly arrange feature components.

## How data moves (TanStack Query)

- **A query** reads: `useDay("2026-10-09")` asks `GET /api/calendar/day?date=...` once and caches the answer under the key `["day", "2026-10-09"]`. Every component asking for the same key shares it; `isPending` and `isError` replace hand-written loading flags.
- **A write** answers the whole expense. Whoever wrote it, a mutation like `useUpdateExpense().mutate({ id, changes })` or a table row saving itself, hands that answer to `expenseChanged` in `features/ledger/api.ts`, which puts it into the cache and marks the keys that may now be out of date (the month's totals, the day, the unreviewed list, receipt cards) as stale, so every page showing them reloads by itself.
- **Polling:** while any receipt is being read, the receipts queries ask again every 3 seconds (`refetchInterval`), so a card turns from 讀取中 to 已入帳 by itself.
- **Signing out:** any 401 makes the client reload the session; `AuthGate` then shows the sign-in page.

## Styling

Tailwind classes go in the markup (`className="flex gap-3 rounded-xl border p-4"`). Colors and corner radius are tokens in `src/index.css` (`--primary`, `--warning`, ...); change one there and everything using it follows, in light and dark mode (dark follows the system). The components in `shared/ui` are shadcn/ui's pattern: our own copies on top of Radix, which handles keyboard, focus and screen readers for dialogs, menus and tabs. `cva` names a component's variants (`<Button variant="outline" size="sm">`); `cn()` merges classes so a later one wins.

## Editing in place (`shared/ui/grid.tsx`)

The expense table and the lines table follow inline-grid-autosave, moved from the old `frontend/`'s `InlineGrid.tsx`. Each row is a `useGridRow(saved, save)`: it holds what was typed on top of what is saved, and decides when to call `save`.

- A saved row calls `save` when you leave a cell (`GridCell` watches focus leaving it, so an amount and its unit in one cell count as one) or press Enter. No timer. Esc puts the cell back.
- One request per row at a time; what you type meanwhile goes after it.
- A failed save keeps what you typed and says why under the row (`RowError`). The same edit is not sent again on every move, only after a change or Enter.
- The new last row (`create: true`) calls `save` only on Enter or its 新增 button.
- Rows report what would be lost (a half-typed new row, an edit that failed) to the page's `useRiskRegistry`, and the page asks before switching the day or closing an expense. The browser itself asks before closing the tab while a row is unsaved.

The tables are wider than a phone: they scroll sideways inside their box (the decision accepted that), and an opened expense's lines stay pinned to that box.

## Adding something

1. The server's new endpoint gets a hook in its feature's `api.ts` (a `useQuery` for a read; a `useMutation` that updates or invalidates keys for a write) and its types in `types.ts`.
2. The UI goes in a component in the feature, built from `shared/ui`.
3. Export what pages need from the feature's `index.ts`, and place it in a page (or a new route in `app/router.tsx`).
4. Test it: `src/test/render.tsx` renders with the real providers and a fake `fetch` that answers by `"METHOD /path"` and records requests.
