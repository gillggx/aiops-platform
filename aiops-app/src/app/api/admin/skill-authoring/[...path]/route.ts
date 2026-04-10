import { NextRequest } from "next/server";

const FASTAPI_BASE = process.env.FASTAPI_BASE_URL ?? "http://localhost:8000";
const TOKEN = process.env.INTERNAL_API_TOKEN ?? "";

function authHeaders(contentType = true) {
  const h: Record<string, string> = { Authorization: `Bearer ${TOKEN}` };
  if (contentType) h["Content-Type"] = "application/json";
  return h;
}

async function proxyJSON(req: NextRequest, method: string, path: string[]) {
  const url = `${FASTAPI_BASE}/api/v1/skill-authoring/${path.join("/")}`;
  const init: RequestInit = { method, headers: authHeaders() };
  if (method !== "GET" && method !== "DELETE") {
    try {
      const body = await req.text();
      if (body) init.body = body;
    } catch { /* empty body */ }
  }
  const res = await fetch(url, init);

  // Stream SSE responses through directly
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("text/event-stream")) {
    return new Response(res.body, {
      status: res.status,
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
      },
    });
  }

  const data = await res.json().catch(() => ({}));
  // Unwrap StandardResponse envelope
  const payload = data.data ?? data;
  return Response.json(payload, { status: res.status });
}

export async function GET(req: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  return proxyJSON(req, "GET", path);
}

export async function POST(req: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  return proxyJSON(req, "POST", path);
}

export async function DELETE(req: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  return proxyJSON(req, "DELETE", path);
}
