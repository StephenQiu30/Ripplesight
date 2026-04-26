import { redirect } from "next/navigation";

export default function HotspotDetailPage({ params }: { params: { id: string } }) {
  redirect(`/app/hotspots/${params.id}`);
}
