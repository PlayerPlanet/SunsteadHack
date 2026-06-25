import { NextResponse } from "next/server";
import { cp, hasControlPlane } from "@/lib/api";
import { mockEscalations } from "@/lib/mock";

export async function GET() {
  if (!hasControlPlane()) return NextResponse.json({ escalations: mockEscalations });

  try {
    const data = await cp<unknown[]>("/escalations");
    return NextResponse.json({ escalations: data ?? [] });
  } catch {
    return NextResponse.json({ escalations: mockEscalations });
  }
}
