import type { Metadata } from "next";
import { connection } from "next/server";

import { EventList } from "@/app/events/components/event-list";

export const metadata: Metadata = {
  title: "已确认事件",
  robots: {
    index: false,
    follow: false,
  },
};

export default async function EventsPage() {
  await connection();

  return <EventList />;
}
