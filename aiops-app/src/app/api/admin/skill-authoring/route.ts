import { NextRequest } from "next/server";

const FASTAPI_BASE = process.env.FASTAPI_BASE_URL ?? "http://localhost:8000";
const TOKEN = process.env.INTERNAL_API_TOKEN ?? "";

function authHeaders() {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${TOKEN}`,
  };
}

export async function GET() {
  const res = await fetch(`${FASTAPI_BASE}/api/v1/skill-authoring`, {
    headers: authHeaders(),
    cache: "no-store",
  });
  const data = await res.json().catch(() => ({}));
  return Response.json(data.data ?? data, { status: res.status });
}

export async function POST(req: NextRequest) {
  const body = await req.text();
  const res = await fetch(`${FASTAPI_BASE}/api/v1/skill-authoring`, {
    method: "POST",
    headers: authHeaders(),
    body,
  });
  const data = await res.json().catch(() => ({}));
  return Response.json(data.data ?? data, { status: res.status });
}
