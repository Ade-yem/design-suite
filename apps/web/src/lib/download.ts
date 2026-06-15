/**
 * @file download.ts
 * @description Small helpers for triggering browser file downloads, including
 * binary/blob downloads fetched from the authenticated API client.
 */

import { apiClient } from "@/lib/api";

/**
 * Trigger a browser download for an in-memory Blob.
 *
 * @param blob     The Blob to download.
 * @param filename Suggested file name for the saved file.
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

/** Parse a `filename="..."` value out of a Content-Disposition header. */
function filenameFromDisposition(disposition: unknown): string | null {
  if (typeof disposition !== "string") return null;
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(disposition);
  return match ? decodeURIComponent(match[1]) : null;
}

/**
 * GET a binary resource from the API as a Blob and trigger a download.
 * Uses the shared {@link apiClient} so the JWT interceptor is applied.
 *
 * @param url          API path to fetch (e.g. `/api/v1/drawings/{id}/export/dxf`).
 * @param fallbackName File name to use if the server sends no Content-Disposition.
 */
export async function downloadFromApi(url: string, fallbackName: string): Promise<void> {
  const response = await apiClient.get(url, { responseType: "blob" });
  const filename =
    filenameFromDisposition(response.headers?.["content-disposition"]) ?? fallbackName;
  downloadBlob(response.data as Blob, filename);
}
