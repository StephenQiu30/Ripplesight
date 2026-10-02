import type { Metadata } from "next";
import { connection } from "next/server";
import { EventDetail } from "@/app/events/[eventId]/components/event-detail";

export const metadata: Metadata = {
  title: "事件详情",
  robots: { index: false, follow: false },
};

export default async function EventDetailPage({
  params,
}: {
  params: Promise<{ eventId: string }>;
}) {
  await connection();
  const { eventId } = await params;
  return <EventDetail key={eventId} eventId={eventId} />;
}
