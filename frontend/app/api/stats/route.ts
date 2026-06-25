import { NextResponse } from "next/server";
import { cp, hasControlPlane } from "@/lib/api";
import { mockStats } from "@/lib/mock";

export async function GET() {
  if (!hasControlPlane()) return NextResponse.json(mockStats);

  try {
    const data = await cp<Record<string, unknown>>("/stats");
    return NextResponse.json(data);
  } catch {
    return NextResponse.json(mockStats);
  }
}
