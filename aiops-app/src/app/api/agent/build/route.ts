import { NextRequest, NextResponse } from "next/server";

const FASTAPI_BASE = process.env.FASTAPI_BASE_URL ?? "http://localhost:8000";
const TOKEN = process.env.INTERNAL_API_TOKEN ?? "";

function authHeaders(): Record<string, string> {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${TOKEN}`,
  };
}

export async function POST(req: NextRequest) {
  const body = await req.json();
  const res = await fetch(`${FASTAPI_BASE}/api/v1/agent/build`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
  });
  const data = await res.json();
  return NextResponse.json(data, { status: res.status });
}
