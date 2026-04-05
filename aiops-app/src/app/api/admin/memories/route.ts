import { NextRequest, NextResponse } from "next/server";

const FASTAPI_BASE = process.env.FASTAPI_BASE_URL ?? "http://localhost:8000";
const TOKEN = process.env.INTERNAL_API_TOKEN ?? "";

function authHeaders() {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${TOKEN}`,
  };
}

export async function GET(req: NextRequest) {
  const status = req.nextUrl.searchParams.get("status");
  const limit = req.nextUrl.searchParams.get("limit") ?? "100";
  const params = new URLSearchParams({ limit });
  if (status) params.set("status", status);

  try {
    const res = await fetch(
      `${FASTAPI_BASE}/api/v1/experience-memory?${params.toString()}`,
      { headers: authHeaders(), cache: "no-store" }
    );
    const data = await res.json();
    return NextResponse.json(data.data ?? []);
  } catch (err) {
    console.error("[memories GET]", err);
    return NextResponse.json([], { status: 200 });
  }
}
