import { CalendarDaysIcon, InboxIcon, LogOutIcon, ReceiptIcon, UserIcon } from "lucide-react";
import type * as React from "react";
import { NavLink, Outlet } from "react-router";

import { useLogout, useSession } from "@/features/auth";
import { useUnreviewed } from "@/features/ledger";
import { CaptureButton, PendingPhotosProvider, ReceiptSheet, useReceipts } from "@/features/receipts";
import { cn } from "@/shared/lib/utils";
import { Button } from "@/shared/ui/button";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuTrigger } from "@/shared/ui/dropdown-menu";

type Item = { to: string; label: string; icon: React.ReactNode; count?: number };

/** The frame around every page: a sidebar on a wide screen, a bottom bar with the camera on a
 * phone; the receipt sheet sits over whichever page is open. */
export function Layout() {
  const receipts = useReceipts(null);
  const unreviewed = useUnreviewed();
  const inboxCount = (receipts.data?.counts.needs_review ?? 0) + (unreviewed.data?.length ?? 0);
  const items: Item[] = [
    { to: "/", label: "收件匣", icon: <InboxIcon />, count: inboxCount },
    { to: "/receipts", label: "收據", icon: <ReceiptIcon />, count: receipts.data?.counts.reading },
    { to: "/calendar", label: "支出", icon: <CalendarDaysIcon /> },
  ];

  return (
    <PendingPhotosProvider>
      <div className="min-h-dvh md:grid md:grid-cols-[15rem_minmax(0,1fr)]">
        <aside className="sticky top-0 hidden h-dvh flex-col border-r bg-card/60 p-4 md:flex">
          <Brand />
          <nav className="mt-6 grid gap-1">
            {items.map((item) => (
              <NavLink key={item.to} to={item.to} end={item.to === "/"}
                className={({ isActive }) => cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors [&_svg]:size-4",
                  isActive ? "bg-accent text-accent-foreground" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                )}>
                {item.icon}
                <span className="flex-1">{item.label}</span>
                {item.count ? <Count value={item.count} /> : null}
              </NavLink>
            ))}
          </nav>
          <div className="mt-auto"><UserMenu wide /></div>
        </aside>

        <div className="flex min-h-dvh flex-col">
          <header className="sticky top-0 z-30 flex items-center border-b bg-background/90 px-4 py-3 backdrop-blur md:hidden">
            <Brand />
          </header>
          <main className="mx-auto w-full max-w-6xl flex-1 px-4 pt-5 pb-28 sm:px-6 md:pt-8 md:pb-10">
            <Outlet />
          </main>
        </div>

        <nav className="fixed inset-x-0 bottom-0 z-30 border-t bg-background/95 pb-[env(safe-area-inset-bottom)] backdrop-blur md:hidden">
          {/* Two tabs, the camera in the middle, two more (the last is the account). */}
          <div className="relative mx-auto grid max-w-md grid-cols-5 items-end">
            {items.slice(0, 2).map((item) => <TabLink key={item.to} item={item} />)}
            <div className="flex justify-center"><CaptureButton className="-mt-5 size-14" /></div>
            {items.slice(2).map((item) => <TabLink key={item.to} item={item} />)}
            <UserMenu tab />
          </div>
        </nav>
      </div>
      <ReceiptSheet />
    </PendingPhotosProvider>
  );
}

function Brand() {
  return (
    <NavLink to="/" className="flex items-center gap-2 font-semibold">
      <img src="/favicon.svg" alt="" className="size-7" />
      CojiDaily
    </NavLink>
  );
}

function Count({ value }: { value: number }) {
  return <span className="bg-primary text-primary-foreground money min-w-5 rounded-full px-1.5 text-center text-xs leading-5">{value}</span>;
}

function TabLink({ item }: { item: Item }) {
  return (
    <NavLink to={item.to} end={item.to === "/"}
      className={({ isActive }) => cn("relative flex flex-col items-center gap-0.5 py-2 text-[11px] [&_svg]:size-5",
        isActive ? "text-primary" : "text-muted-foreground")}>
      {item.icon}
      {item.label}
      {item.count ? <span className="absolute top-1 left-1/2 ml-2"><Count value={item.count} /></span> : null}
    </NavLink>
  );
}

function UserMenu({ wide = false, tab = false }: { wide?: boolean; tab?: boolean }) {
  const user = useSession().data?.user;
  const logout = useLogout();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {tab ? (
          <button type="button" className="text-muted-foreground flex flex-col items-center gap-0.5 py-2 text-[11px] [&_svg]:size-5">
            <UserIcon />帳號
          </button>
        ) : (
          <Button variant="ghost" className={cn(wide && "w-full justify-start")} aria-label="帳號">
            <UserIcon />
            <span className="truncate">{user?.username}</span>
          </Button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align={wide ? "start" : "end"} side={tab ? "top" : "bottom"}>
        <DropdownMenuLabel>{user?.username}</DropdownMenuLabel>
        <DropdownMenuItem onSelect={() => logout.mutate()}><LogOutIcon /> 登出</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
