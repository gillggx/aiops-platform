import { NextRequest, NextResponse } from "next/server";

const FASTAPI_BASE = process.env.FASTAPI_BASE_URL ?? "http://localhost:8000";
const TOKEN = process.env.INTERNAL_API_TOKEN ?? "";

export async function POST(req: NextRequest) {
  const body = await req.json();
  try {
    const res = await fetch(`${FASTAPI_BASE}/api/v1/my-skills/try-run-draft`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${TOKEN}`,
      },
      body: JSON.stringify(body),
    });
    const data = await res.json();
    if (!res.ok) {
      return NextResponse.json(
        { error: data.message ?? "try-run failed" },
        { status: res.status }
      );
    }
    return NextResponse.json(data.data ?? data);
  } catch (err) {
    console.error("[my-skills try-run-draft]", err);
    return NextResponse.json({ error: "try-run failed" }, { status: 500 });
  }
}
