import { create } from "zustand";
import type { Block, Document, DocumentSummary, TextBlock, TableBlock } from "@/types/document";
import { api } from "@/lib/api";

interface DocumentState {
  document: Document | null;
  recentDocuments: DocumentSummary[];
  isUploading: boolean;
  isSavingBlock: boolean;
  setDocument: (doc: Document | null) => void;
  upload: (file: File) => Promise<Document>;
  refreshRecent: () => Promise<void>;
  loadDocument: (id: string) => Promise<void>;
  updateBlockLocal: (blockId: string, patch: Partial<TextBlock | TableBlock>) => void;
  saveBlock: (
    blockId: string,
    payload: { translated_text?: string; translated_rows?: string[][] },
  ) => Promise<void>;
}

function patchBlockInDocument(
  doc: Document,
  blockId: string,
  patch: Partial<TextBlock | TableBlock>,
): Document {
  return {
    ...doc,
    pages: doc.pages.map((page) => ({
      ...page,
      blocks: page.blocks.map((block) =>
        block.id === blockId ? ({ ...block, ...patch } as Block) : block,
      ),
    })),
  };
}

export const useDocumentStore = create<DocumentState>((set, get) => ({
  document: null,
  recentDocuments: [],
  isUploading: false,
  isSavingBlock: false,

  setDocument: (doc) => set({ document: doc }),

  upload: async (file) => {
    set({ isUploading: true });
    try {
      const doc = await api.uploadDocument(file);
      set({ document: doc });
      const recent = await api.listDocuments();
      set({ recentDocuments: recent });
      return doc;
    } finally {
      set({ isUploading: false });
    }
  },

  refreshRecent: async () => {
    const recent = await api.listDocuments();
    set({ recentDocuments: recent });
  },

  loadDocument: async (id) => {
    const doc = await api.getDocument(id);
    set({ document: doc });
  },

  updateBlockLocal: (blockId, patch) => {
    const doc = get().document;
    if (!doc) return;
    set({ document: patchBlockInDocument(doc, blockId, patch) });
  },

  saveBlock: async (blockId, payload) => {
    const doc = get().document;
    if (!doc) return;
    set({ isSavingBlock: true });
    try {
      const updated = await api.updateBlock(doc.id, blockId, payload);
      set({ document: updated });
    } finally {
      set({ isSavingBlock: false });
    }
  },
}));
