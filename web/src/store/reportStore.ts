/** 报告域：七章节 payload、批注、版本与导出状态。 */

import { create } from "zustand";
import { persist } from "zustand/middleware";

export interface Annotation {
  id: string;
  anchor: string;
  content: string;
  version: number;
  author: string;
  createdAt: string;
}

export interface ReportPayload {
  meta: Record<string, unknown>;
  sections: Array<{ id: string; title: string; content: Record<string, unknown> }>;
}

interface ReportState {
  reportId: number | null;
  payload: ReportPayload | null;
  annotations: Annotation[];
  versions: number[];
  exportStatus: "idle" | "rendering" | "done" | "failed";
  setReport: (reportId: number, payload: ReportPayload, version: number) => void;
  addAnnotation: (annotation: Omit<Annotation, "id" | "createdAt">) => void;
  setExportStatus: (status: ReportState["exportStatus"]) => void;
  reset: () => void;
}

export const useReportStore = create<ReportState>()(
  persist(
    (set, get) => ({
      reportId: null,
      payload: null,
      annotations: [],
      versions: [],
      exportStatus: "idle",

      setReport: (reportId, payload, version) =>
        set({
          reportId,
          payload,
          versions: Array.from(new Set([...get().versions, version])).sort((a, b) => a - b),
        }),

      addAnnotation: (annotation) =>
        set({
          annotations: [
            ...get().annotations,
            {
              ...annotation,
              id: `anno-${Date.now()}`,
              createdAt: new Date().toISOString(),
            },
          ],
        }),

      setExportStatus: (exportStatus) => set({ exportStatus }),
      reset: () => set({ reportId: null, payload: null, annotations: [], versions: [], exportStatus: "idle" }),
    }),
    { name: "ct-report" },
  ),
);
