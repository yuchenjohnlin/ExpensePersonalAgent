import { createBrowserRouter, Link } from "react-router";

import { AuthGate } from "@/features/auth";
import { CalendarPage } from "@/pages/CalendarPage";
import { InboxPage } from "@/pages/InboxPage";
import { ReceiptsPage } from "@/pages/ReceiptsPage";
import { Button } from "@/shared/ui/button";
import { EmptyState } from "@/shared/ui/feedback";

import { Layout } from "./Layout";

export const routes = [
  {
    element: <AuthGate><Layout /></AuthGate>,
    children: [
      { index: true, element: <InboxPage /> },
      { path: "receipts", element: <ReceiptsPage /> },
      { path: "calendar", element: <CalendarPage /> },
      {
        path: "*",
        element: (
          <EmptyState title="沒有這一頁">
            <Button asChild variant="outline" className="mt-3"><Link to="/">回收件匣</Link></Button>
          </EmptyState>
        ),
      },
    ],
  },
];

export const router = createBrowserRouter(routes);
