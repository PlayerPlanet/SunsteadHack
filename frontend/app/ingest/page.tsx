"use client";
import { useState, useRef } from "react";
import { AlertCircle, CheckCircle, Upload, X } from "lucide-react";
import TopBar from "@/components/TopBar";

type PreviewState = {
  headers: string[];
  rowCount: number;
  distinctDocuments: number;
  isValid: boolean;
  rows: string[][];
};

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

export default function IngestPage() {
  const [name, setName] = useState("");
  const [objective, setObjective] = useState(
    "Maximize field-extraction F1 on held-out bond term sheets"
  );

  const [goldFile, setGoldFile] = useState<File | null>(null);
  const [goldPreview, setGoldPreview] = useState<PreviewState | null>(null);

  const [splitsFile, setSplitsFile] = useState<File | null>(null);
  const [interpretationFile, setInterpretationFile] = useState<File | null>(null);
  const [documentsFile, setDocumentsFile] = useState<File | null>(null);

  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{
    task_id?: string;
    dataset_path?: string;
    n_documents?: number;
    n_fields?: number;
    n_holdout?: number;
    n_interpretation?: number;
    warnings?: string[];
    mock?: boolean;
    error?: string;
  } | null>(null);

  const goldInputRef = useRef<HTMLInputElement>(null);

  async function onGoldFileSelect(file: File) {
    setGoldFile(file);
    setGoldPreview(null);
    setResult(null);

    try {
      const text = await file.text();
      const { headers, rows } = parseCSV(text);

      const hasDocId = headers.includes("document_id");
      const hasFieldName = headers.includes("field_name");
      const hasGoldValue = headers.includes("gold_value");

      const docIdIdx = headers.indexOf("document_id");
      const documentIds = rows
        .map((r) => r[docIdIdx] ?? "")
        .filter(Boolean);
      const distinctDocuments = new Set(documentIds).size;

      setGoldPreview({
        headers,
        rowCount: rows.length,
        distinctDocuments,
        isValid: hasDocId && hasFieldName && hasGoldValue,
        rows: rows.slice(0, 8), // First 8 rows for preview
      });
    } catch (err) {
      setGoldPreview({
        headers: [],
        rowCount: 0,
        distinctDocuments: 0,
        isValid: false,
        rows: [],
      });
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !goldFile || !goldPreview?.isValid) return;

    setSubmitting(true);
    setResult(null);

    try {
      const form = new FormData();
      form.append("name", name.trim());
      form.append("objective", objective.trim());
      form.append("gold", goldFile);
      if (splitsFile) form.append("splits", splitsFile);
      if (interpretationFile) form.append("interpretation", interpretationFile);
      if (documentsFile) form.append("documents", documentsFile);

      const res = await fetch("/api/ingest", {
        method: "POST",
        body: form,
      });

      const data = await res.json();
      setResult(data);

      if (data.task_id && !data.error) {
        // Reset form on success
        setName("");
        setObjective("Maximize field-extraction F1 on held-out bond term sheets");
        setGoldFile(null);
        setGoldPreview(null);
        setSplitsFile(null);
        setInterpretationFile(null);
        setDocumentsFile(null);
        if (goldInputRef.current) goldInputRef.current.value = "";
      }
    } catch (err: any) {
      setResult({ error: err.message ?? "Unknown error" });
    } finally {
      setSubmitting(false);
    }
  }

  const canSubmit =
    name.trim() &&
    objective.trim() &&
    goldFile &&
    goldPreview?.isValid &&
    !submitting;

  return (
    <>
      <TopBar title="Ingest dataset" />
      <main className="flex-1 p-6 space-y-6 overflow-y-auto">
        {/* Description */}
        <p className="text-sm text-gray-600">
          Create a held-out bond-extraction benchmark from gold-field CSVs.
          The agent auto-extracts objective fields and escalates interpretation clauses.
        </p>

        {/* Result panel */}
        {result && (
          <div
            className={`border rounded-xl p-6 space-y-4 ${
              result.error
                ? "bg-red-50 border-red-200"
                : "bg-emerald-50 border-emerald-200"
            }`}
          >
            <div className="flex items-start gap-3">
              {result.error ? (
                <AlertCircle className="w-5 h-5 text-red-500 flex-shrink-0 mt-0.5" />
              ) : (
                <CheckCircle className="w-5 h-5 text-emerald-600 flex-shrink-0 mt-0.5" />
              )}
              <div className="flex-1 min-w-0">
                {result.error ? (
                  <>
                    <p
                      className={`font-medium ${
                        result.error
                          ? "text-red-800"
                          : "text-emerald-800"
                      }`}
                    >
                      {result.error ? "Error" : "Success"}
                    </p>
                    <p className="text-sm text-red-700 mt-1">{result.error}</p>
                  </>
                ) : (
                  <>
                    <div className="flex items-center gap-2 flex-wrap mb-3">
                      <p className="font-medium text-emerald-800">
                        Dataset ingested
                      </p>
                      {result.mock && (
                        <span className="text-xs font-mono bg-amber-100 text-amber-700 px-2 py-0.5 rounded border border-amber-200">
                          mock
                        </span>
                      )}
                    </div>
                    <div className="space-y-1 text-sm text-emerald-700">
                      <p>
                        <span className="font-semibold">Task ID:</span>{" "}
                        <span className="font-mono">{result.task_id}</span>
                      </p>
                      <p>
                        <span className="font-semibold">Dataset path:</span>{" "}
                        <span className="font-mono text-xs">{result.dataset_path}</span>
                      </p>
                      <p>
                        <span className="font-semibold">Documents:</span> {result.n_documents}
                      </p>
                      <p>
                        <span className="font-semibold">Fields:</span> {result.n_fields}
                      </p>
                      <p>
                        <span className="font-semibold">Held-out:</span> {result.n_holdout}
                      </p>
                      <p>
                        <span className="font-semibold">Interpretation clauses:</span>{" "}
                        {result.n_interpretation}
                      </p>
                    </div>
                    {result.warnings && result.warnings.length > 0 && (
                      <div className="mt-3 pt-3 border-t border-emerald-200 space-y-1 text-xs text-emerald-600">
                        {result.warnings.map((w, i) => (
                          <p key={i}>⚠ {w}</p>
                        ))}
                      </div>
                    )}
                    <div className="mt-4 flex gap-3">
                      <a
                        href={`/runs?task=${result.task_id}`}
                        className="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-lg bg-emerald-600 text-white font-medium hover:bg-emerald-700 transition-colors"
                      >
                        View runs →
                      </a>
                      <a
                        href="/"
                        className="inline-flex items-center gap-2 px-4 py-2 text-sm rounded-lg border border-emerald-300 text-emerald-700 font-medium hover:bg-emerald-50 transition-colors"
                      >
                        Dashboard
                      </a>
                    </div>
                  </>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-6">
          {/* Benchmark name */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6 space-y-4">
            <div>
              <label className="block text-sm font-semibold text-gray-900 mb-2">
                Benchmark name
              </label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="my-bond-extraction-v1"
                className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
              />
            </div>

            <div>
              <label className="block text-sm font-semibold text-gray-900 mb-2">
                Objective
              </label>
              <input
                type="text"
                value={objective}
                onChange={(e) => setObjective(e.target.value)}
                placeholder="Maximize field-extraction F1 on held-out bond term sheets"
                className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-navy focus:border-transparent"
              />
            </div>
          </div>

          {/* File inputs */}
          <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-6 space-y-6">
            {/* Gold fields (required) */}
            <div>
              <label className="block text-sm font-semibold text-gray-900 mb-2">
                Gold fields CSV <span className="text-red-500">*</span>
              </label>
              <p className="text-xs text-gray-500 mb-3">
                Required columns: <code className="bg-gray-100 px-1.5 py-0.5 rounded font-mono">document_id</code>, <code className="bg-gray-100 px-1.5 py-0.5 rounded font-mono">field_name</code>, <code className="bg-gray-100 px-1.5 py-0.5 rounded font-mono">gold_value</code>
              </p>
              <input
                ref={goldInputRef}
                type="file"
                accept=".csv"
                onChange={(e) => e.target.files?.[0] && onGoldFileSelect(e.target.files[0])}
                className="w-full border border-gray-200 rounded-lg px-4 py-2.5 text-sm text-gray-600 file:mr-3 file:px-3 file:py-1.5 file:rounded file:border-0 file:text-sm file:font-medium file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200 transition-colors"
              />

              {/* Gold preview */}
              {goldPreview && (
                <div className="mt-4 space-y-3">
                  <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-50 border border-gray-100">
                    {goldPreview.isValid ? (
                      <CheckCircle className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                    ) : (
                      <AlertCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                    )}
                    <div className="text-sm">
                      <p
                        className={`font-medium ${
                          goldPreview.isValid
                            ? "text-emerald-700"
                            : "text-red-700"
                        }`}
                      >
                        {goldPreview.isValid
                          ? "Valid gold CSV"
                          : "Invalid CSV"}
                      </p>
                      {!goldPreview.isValid && (
                        <p className="text-xs text-red-600 mt-1">
                          Missing required columns. Expected: document_id, field_name, gold_value
                        </p>
                      )}
                      {goldPreview.isValid && (
                        <p className="text-xs text-gray-600 mt-1">
                          {goldPreview.rowCount} rows, {goldPreview.distinctDocuments} documents
                        </p>
                      )}
                    </div>
                  </div>

                  {goldPreview.isValid && goldPreview.rows.length > 0 && (
                    <div className="overflow-x-auto border border-gray-200 rounded-lg">
                      <table className="w-full text-xs">
                        <thead className="bg-gray-50 border-b border-gray-200">
                          <tr>
                            {goldPreview.headers.map((h) => (
                              <th
                                key={h}
                                className="px-3 py-2 text-left font-semibold text-gray-700"
                              >
                                {h}
                              </th>
                            ))}
                          </tr>
                        </thead>
                        <tbody className="divide-y divide-gray-100">
                          {goldPreview.rows.map((row, i) => (
                            <tr key={i} className="hover:bg-gray-50">
                              {goldPreview.headers.map((h, j) => (
                                <td
                                  key={`${i}-${j}`}
                                  className="px-3 py-2 text-gray-800"
                                >
                                  {row[j] ?? "—"}
                                </td>
                              ))}
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Optional files */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
              <div>
                <label className="block text-sm font-semibold text-gray-900 mb-2">
                  Splits CSV <span className="text-gray-400 text-xs">(optional)</span>
                </label>
                <p className="text-xs text-gray-500 mb-2">
                  Columns: <code className="bg-gray-100 px-1 rounded font-mono">document_id</code>, <code className="bg-gray-100 px-1 rounded font-mono">split</code>
                </p>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setSplitsFile(e.target.files?.[0] ?? null)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-600 file:mr-2 file:px-2 file:py-1 file:rounded file:border-0 file:text-xs file:font-medium file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200 transition-colors"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-900 mb-2">
                  Interpretation CSV <span className="text-gray-400 text-xs">(optional)</span>
                </label>
                <p className="text-xs text-gray-500 mb-2">
                  Columns: <code className="bg-gray-100 px-1 rounded font-mono">document_id</code>, <code className="bg-gray-100 px-1 rounded font-mono">clause_or_question</code>
                </p>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setInterpretationFile(e.target.files?.[0] ?? null)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-600 file:mr-2 file:px-2 file:py-1 file:rounded file:border-0 file:text-xs file:font-medium file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200 transition-colors"
                />
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-900 mb-2">
                  Documents CSV <span className="text-gray-400 text-xs">(optional)</span>
                </label>
                <p className="text-xs text-gray-500 mb-2">
                  Columns: <code className="bg-gray-100 px-1 rounded font-mono">document_id</code>, <code className="bg-gray-100 px-1 rounded font-mono">text</code>
                </p>
                <input
                  type="file"
                  accept=".csv"
                  onChange={(e) => setDocumentsFile(e.target.files?.[0] ?? null)}
                  className="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm text-gray-600 file:mr-2 file:px-2 file:py-1 file:rounded file:border-0 file:text-xs file:font-medium file:bg-gray-100 file:text-gray-700 hover:file:bg-gray-200 transition-colors"
                />
              </div>
            </div>
          </div>

          {/* Submit */}
          <div className="flex gap-3">
            <button
              type="submit"
              disabled={!canSubmit}
              className="flex items-center gap-2 px-4 py-2.5 text-sm rounded-lg bg-navy text-white font-medium hover:bg-navy-dark transition-colors disabled:opacity-60 disabled:cursor-not-allowed"
            >
              <Upload className="w-4 h-4" />
              {submitting ? "Ingesting…" : "Ingest dataset"}
            </button>
          </div>
        </form>
      </main>
    </>
  );
}
