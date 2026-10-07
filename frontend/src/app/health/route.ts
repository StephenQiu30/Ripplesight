export const dynamic = "force-dynamic";

export function GET() {
  return Response.json(
    { status: "ok", service: "ripplesight-frontend" },
    { headers: { "Cache-Control": "no-store" } },
  );
}
