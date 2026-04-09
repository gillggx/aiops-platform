import { NextRequest } from "next/server";

const FASTAPI_BASE = process.env.FASTAPI_BASE_URL ?? "http://localhost:8000";
const TOKEN = process.env.INTERNAL_API_TOKEN ?? "";

export async function POST(req: NextRequest) {
  const body = await req.json();
  const upstream = await fetch(
    `${FASTAPI_BASE}/api/v1/my-skills/generate-steps/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${TOKEN}`,
      },
      body: JSON.stringify(body),
      // @ts-expect-error: Node.js fetch duplex option
      duplex: "half",
    }
  );

  if (!upstream.ok) {
    return new Response(
      JSON.stringify({ error: `Backend responded with ${upstream.status}` }),
      { status: upstream.status, headers: { "Content-Type": "application/json" } }
    );
  }

  return new Response(upstream.body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache",
      "X-Accel-Buffering": "no",
    },
  });
}
