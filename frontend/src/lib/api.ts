import { API_BASE } from "./utils";
import type {
  Document,
  DocumentSummary,
  HealthResponse,
  PipelineProgress,
  TranslatorSettings,
} from "@/types/document";

function parseApiError(body: string, statusText: string): string {
  try {
    const parsed = JSON.parse(body) as { detail?: string | { msg?: string }[] };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail;
    }
    if (Array.isArray(parsed.detail) && parsed.detail[0]?.msg) {
      return parsed.detail.map((d) => d.msg).join("; ");
    }
  } catch {
    // not JSON
  }
  return body.trim() || statusText;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(parseApiError(detail, res.statusText));
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>("/health"),

  listDocuments: () => request<DocumentSummary[]>("/documents"),

  getDocument: (id: string) => request<Document>(`/documents/${id}`),

  uploadDocument: async (file: File): Promise<Document> => {
    const form = new FormData();
    form.append("file", file);
    const res = await fetch(`${API_BASE}/documents/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    return data.document as Document;
  },

  deleteDocument: (id: string) =>
    request<{ deleted: boolean }>(`/documents/${id}`, { method: "DELETE" }),

  processDocument: (
    id: string,
    opts?: {
      source_language?: string;
      target_language?: string;
      skip_translation?: boolean;
    },
  ) =>
    request<Document>(`/documents/${id}/process`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(opts ?? {}),
    }),

  exportDocument: (id: string, format: "pdf" | "docx" | "html", useTranslated = true) =>
    request<{ download_url: string; format: string }>(`/documents/${id}/export`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ format, use_translated: useTranslated }),
    }),

  downloadUrl: (path: string) => `${API_BASE.replace("/api/v1", "")}${path}`,

  thumbnailUrl: (documentId: string, pageNumber: number) =>
    `${API_BASE}/documents/${documentId}/thumbnail/${pageNumber}`,

  rasterUrl: (documentId: string, pageNumber: number) =>
    `${API_BASE}/documents/${documentId}/raster/${pageNumber}`,

  translatedRasterUrl: (documentId: string, pageNumber: number) =>
    `${API_BASE}/documents/${documentId}/raster/${pageNumber}?variant=translated`,

  strippedRasterUrl: (documentId: string, pageNumber: number) =>
    `${API_BASE}/documents/${documentId}/raster/${pageNumber}?variant=stripped`,

  translateDocument: (
    id: string,
    opts?: {
      source_language?: string;
      target_language?: string;
      reconstruct?: boolean;
      skip_edited?: boolean;
      page_numbers?: number[];
      block_ids?: string[];
    },
  ) =>
    request<Document>(`/documents/${id}/translate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reconstruct: true, skip_edited: true, ...opts }),
    }),

  updateBlock: (
    documentId: string,
    blockId: string,
    payload: { translated_text?: string; translated_rows?: string[][] },
  ) =>
    request<Document>(`/documents/${documentId}/blocks/${blockId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),

  reconstructDocument: (id: string, pageNumbers?: number[]) =>
    request<Document>(`/documents/${id}/reconstruct`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page_numbers: pageNumbers ?? null }),
    }),

  getGlossary: () => request<Record<string, string>>("/settings/glossary"),

  saveGlossary: (entries: Record<string, string>) =>
    request<Record<string, string>>("/settings/glossary", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entries }),
    }),

  assetUrl: (documentId: string, assetName: string) =>
    `${API_BASE}/documents/${documentId}/assets/${assetName}`,

  getSettings: () =>
    request<{ translator: TranslatorSettings }>("/settings").then((r) => r.translator),

  saveSettings: (settings: TranslatorSettings) =>
    request<{ translator: TranslatorSettings }>("/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings),
    }).then((r) => r.translator),

  testConnection: (provider?: string) =>
    request<{ available: boolean; message: string; models: string[] }>(
      `/settings/test-connection${provider ? `?provider=${provider}` : ""}`,
      { method: "POST" },
    ),

  streamProcess: (
    id: string,
    onProgress: (p: PipelineProgress) => void,
    onComplete: (doc: Document) => void,
    onError: (msg: string) => void,
    opts?: { source_language?: string; target_language?: string; skip_translation?: boolean },
  ): (() => void) => {
    const params = new URLSearchParams();
    if (opts?.source_language) params.set("source_language", opts.source_language);
    if (opts?.target_language) params.set("target_language", opts.target_language);
    if (opts?.skip_translation) params.set("skip_translation", "true");
    const url = `${API_BASE}/documents/${id}/process/stream?${params}`;
    const es = new EventSource(url);

    es.addEventListener("progress", (e) => {
      onProgress(JSON.parse(e.data) as PipelineProgress);
    });
    es.addEventListener("complete", (e) => {
      onComplete(JSON.parse(e.data) as Document);
      es.close();
    });
    es.addEventListener("error", (e) => {
      if (e instanceof MessageEvent) {
        onError(JSON.parse(e.data).message);
      } else {
        onError("Processing stream failed");
      }
      es.close();
    });

    return () => es.close();
  },
};
