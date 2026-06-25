import { NextResponse } from "next/server";
import { cp, hasControlPlane } from "@/lib/api";
import { mockBoundaryCurve, mockLongitudinal } from "@/lib/mock";

export async function GET() {
  if (!hasControlPlane()) {
    return NextResponse.json({ spatial: mockBoundaryCurve, longitudinal: mockLongitudinal });
  }

  try {
    const data = await cp<{ spatial: unknown[]; longitudinal: unknown[]; proxy_caveat?: string }>("/boundary");
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ spatial: mockBoundaryCurve, longitudinal: mockLongitudinal });
  }
}
