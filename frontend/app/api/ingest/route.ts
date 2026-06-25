import { NextResponse } from "next/server";
import { cp, hasControlPlane } from "@/lib/api";

function parseCSV(text: string): { headers: string[]; rows: string[][] } {
  const lines = text.trim().split("\n");
  if (lines.length === 0) return { headers: [], rows: [] };

  const headers = lines[0].split(",").map((h) => h.trim());
  const rows: string[][] = [];

  for (let i = 1; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim()) continue;
    const parts = line.split(",").map((p) => p.trim());
    rows.push(parts);
  }

  return { headers, rows };
}

function countDistinct(values: string[]): number {
  return new Set(values).size;
}

function slug(name: string): string {
  return name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export async function POST(req: Request) {
  try {
    const formData = await req.formData();

    const name = String(formData.get("name") ?? "").trim();
    const objective = String(formData.get("objective") ?? "").trim();
    const goldFile = formData.get("gold") as File | null;
    const splitsFile = formData.get("splits") as File | null;
    const interpretationFile = formData.get("interpretation") as File | null;
    const documentsFile = formData.get("documents") as File | null;

    if (!name) {
      return NextResponse.json({ error: "name is required" }, { status: 400 });
    }
    if (!objective) {
      return NextResponse.json({ error: "objective is required" }, { status: 400 });
    }
    if (!goldFile) {
      return NextResponse.json({ error: "gold_fields.csv is required" }, { status: 400 });
    }

    // Read file contents
    const goldCSV = await goldFile.text();
    const splitsCSV = splitsFile ? await splitsFile.text() : null;
    const interpretationCSV = interpretationFile ? await interpretationFile.text() : null;
    const documentsCSV = documentsFile ? await documentsFile.text() : null;

    // Parse gold CSV to validate and compute mock stats
    const { headers: goldHeaders, rows: goldRows } = parseCSV(goldCSV);
    const hasDocId = goldHeaders.includes("document_id");
    const hasFieldName = goldHeaders.includes("field_name");
    const hasGoldValue = goldHeaders.includes("gold_value");

    if (!hasDocId || !hasFieldName || !hasGoldValue) {
      return NextResponse.json(
        { error: "gold_fields.csv must have columns: document_id, field_name, gold_value" },
        { status: 400 }
      );
    }

    // Extract distinct counts for mock response
    const docIdCol = goldHeaders.indexOf("document_id");
    const fieldNameCol = goldHeaders.indexOf("field_name");
    const documentIds = goldRows.map((r) => r[docIdCol] ?? "").filter(Boolean);
    const fieldNames = goldRows.map((r) => r[fieldNameCol] ?? "").filter(Boolean);
    const distinctDocuments = countDistinct(documentIds);
    const distinctFields = countDistinct(fieldNames);

    // Parse interpretation CSV if provided
    let distinctInterpretations = 0;
    if (interpretationCSV) {
      const { rows: interpRows, headers: interpHeaders } = parseCSV(interpretationCSV);
      if (interpHeaders.length > 1) {
        const clauseCol = 1; // second column
        const clauses = interpRows.map((r) => r[clauseCol] ?? "").filter(Boolean);
        distinctInterpretations = clauses.length;
      }
    }

    // If no control plane, return mock
    if (!hasControlPlane()) {
      const taskId = slug(name) || `bond-${Date.now()}`;
      return NextResponse.json({
        task_id: taskId,
        dataset_path: "(mock)",
        n_documents: distinctDocuments,
        n_fields: distinctFields,
        n_holdout: 0,
        n_interpretation: distinctInterpretations,
        warnings: ["control plane not configured — mock only"],
        mock: true,
      });
    }

    // Forward to control plane
    try {
      const cpResponse = await cp<{
        task_id: string;
        dataset_path: string;
        n_documents: number;
        n_fields: number;
        n_holdout: number;
        n_interpretation: number;
        warnings?: string[];
      }>("/ingest/bond", {
        method: "POST",
        body: JSON.stringify({
          name,
          objective,
          gold_csv: goldCSV,
          splits_csv: splitsCSV,
          interpretation_csv: interpretationCSV,
          documents_csv: documentsCSV,
        }),
      });

      return NextResponse.json(cpResponse);
    } catch (cpErr: any) {
      const errText = cpErr.message ?? String(cpErr);
      // Parse control plane error response format: "Control plane /ingest/bond → 400: {json}"
      if (errText.includes(" → 400: ")) {
        try {
          const jsonPart = errText.split(" → 400: ")[1];
          const parsed = JSON.parse(jsonPart);
          if (parsed.detail) {
            return NextResponse.json({ error: parsed.detail }, { status: 400 });
          }
        } catch {
          // Fall through to generic error
        }
      }
      return NextResponse.json(
        { error: `Control plane error: ${errText}` },
        { status: 500 }
      );
    }
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message ?? "Unknown error" },
      { status: 500 }
    );
  }
}
