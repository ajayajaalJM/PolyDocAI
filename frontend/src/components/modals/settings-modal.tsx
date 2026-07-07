"use client";

import * as Dialog from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "@/components/ui/toast-provider";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { LANGUAGES } from "@/lib/languages";
import { useSettingsStore } from "@/stores/settings-store";
import { useUIStore } from "@/stores/ui-store";

export function SettingsModal() {
  const open = useUIStore((s) => s.settingsOpen);
  const setOpen = useUIStore((s) => s.setSettingsOpen);
  const { translator, setTranslator } = useSettingsStore();
  const [local, setLocal] = useState(translator);
  const [testing, setTesting] = useState(false);
  const [ollamaModels, setOllamaModels] = useState<string[]>([]);
  const [glossaryText, setGlossaryText] = useState("");

  useEffect(() => {
    if (open) {
      api.getSettings().then(setLocal).catch(() => setLocal(translator));
      api.getGlossary()
        .then((entries) => {
          const lines = Object.entries(entries).map(([k, v]) => `${k}=${v}`);
          setGlossaryText(lines.join("\n"));
        })
        .catch(() => setGlossaryText(""));
      api.testConnection("ollama")
        .then((result) => setOllamaModels(result.models))
        .catch(() => setOllamaModels([]));
    }
  }, [open, translator]);

  const save = async () => {
    try {
      const saved = await api.saveSettings(local);
      const entries: Record<string, string> = {};
      for (const line of glossaryText.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed || !trimmed.includes("=")) continue;
        const [key, ...rest] = trimmed.split("=");
        entries[key.trim()] = rest.join("=").trim();
      }
      await api.saveGlossary(entries);
      setTranslator(saved);
      setOpen(false);
      toast.success("Settings saved");
    } catch {
      toast.error("Failed to save settings");
    }
  };

  const testConnection = async () => {
    setTesting(true);
    try {
      const result = await api.testConnection(local.provider);
      if (result.models.length) setOllamaModels(result.models);
      if (result.available) {
        toast.success("Connected", { description: result.message });
      } else {
        toast.warning("Unavailable", { description: result.message });
      }
    } finally {
      setTesting(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-50 bg-black/40" />
        <Dialog.Content className="fixed left-1/2 top-1/2 z-50 flex max-h-[min(90dvh,640px)] w-[calc(100%-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 flex-col overflow-hidden rounded-xl border border-border bg-card shadow-xl sm:w-full">
          <div className="flex shrink-0 items-center justify-between border-b border-border px-4 py-3">
            <Dialog.Title className="text-lg font-semibold">Settings</Dialog.Title>
            <Dialog.Close asChild>
              <Button variant="ghost" size="icon" aria-label="Close">
                <X className="h-4 w-4" />
              </Button>
            </Dialog.Close>
          </div>

          <div className="flex-1 overflow-y-auto px-4 py-4">
            <div className="space-y-4">
            <div>
              <label className="text-sm font-medium" htmlFor="provider">
                Translation provider
              </label>
              <select
                id="provider"
                value={local.provider}
                onChange={(e) =>
                  setLocal({
                    ...local,
                    provider: e.target.value as typeof local.provider,
                  })
                }
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
              >
                <option value="ollama">Ollama (LLM)</option>
                <option value="nmt">NMT (Argos — recommended)</option>
                <option value="deepl">DeepL (cloud)</option>
                <option value="openai_compatible">LM Studio / OpenAI-compatible</option>
                <option value="noop">Pass-through (no translation)</option>
              </select>
            </div>

            {local.provider === "ollama" && (
              <>
                <div>
                  <label className="text-sm font-medium" htmlFor="ollama-url">
                    Ollama URL
                  </label>
                  <input
                    id="ollama-url"
                    value={local.ollama_base_url}
                    onChange={(e) => setLocal({ ...local, ollama_base_url: e.target.value })}
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium" htmlFor="ollama-model">
                    Model
                  </label>
                  {ollamaModels.length > 0 ? (
                    <select
                      id="ollama-model"
                      value={local.ollama_model}
                      onChange={(e) => setLocal({ ...local, ollama_model: e.target.value })}
                      className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                    >
                      {!ollamaModels.includes(local.ollama_model) && (
                        <option value={local.ollama_model}>
                          {local.ollama_model} (not installed)
                        </option>
                      )}
                      {ollamaModels.map((model) => (
                        <option key={model} value={model}>{model}</option>
                      ))}
                    </select>
                  ) : (
                    <input
                      id="ollama-model"
                      value={local.ollama_model}
                      onChange={(e) => setLocal({ ...local, ollama_model: e.target.value })}
                      className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                    />
                  )}
                  {ollamaModels.length > 0 && !ollamaModels.includes(local.ollama_model) && (
                    <p className="mt-1 text-xs text-warning">
                      {local.ollama_model} is not installed. Pick a model from the list or run{" "}
                      <code className="rounded bg-muted px-1">ollama pull {local.ollama_model}</code>.
                    </p>
                  )}
                </div>
              </>
            )}

            {local.provider === "openai_compatible" && (
              <>
                <div>
                  <label className="text-sm font-medium" htmlFor="openai-url">
                    API base URL
                  </label>
                  <input
                    id="openai-url"
                    value={local.openai_compatible_base_url}
                    onChange={(e) =>
                      setLocal({ ...local, openai_compatible_base_url: e.target.value })
                    }
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  />
                </div>
                <div>
                  <label className="text-sm font-medium" htmlFor="openai-model">
                    Model
                  </label>
                  <input
                    id="openai-model"
                    value={local.openai_compatible_model}
                    onChange={(e) =>
                      setLocal({ ...local, openai_compatible_model: e.target.value })
                    }
                    className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  />
                </div>
              </>
            )}

            {local.provider === "deepl" && (
              <div>
                <label className="text-sm font-medium" htmlFor="deepl-key">
                  DeepL API key
                </label>
                <input
                  id="deepl-key"
                  type="password"
                  value={local.deepl_api_key ?? ""}
                  onChange={(e) => setLocal({ ...local, deepl_api_key: e.target.value })}
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                  placeholder="Your DeepL auth key"
                />
              </div>
            )}

            {local.provider === "nmt" && (
              <p className="text-xs text-muted-foreground">
                Uses Argos Translate offline. Language pairs are downloaded automatically on first use.
              </p>
            )}

            <div>
              <label className="text-sm font-medium" htmlFor="glossary">
                Glossary (term=translation, one per line)
              </label>
              <textarea
                id="glossary"
                value={glossaryText}
                onChange={(e) => setGlossaryText(e.target.value)}
                rows={4}
                className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 font-mono text-xs"
                placeholder={"Company=Empresa\nAPI=API"}
              />
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <div>
                <label className="text-sm font-medium" htmlFor="source-lang">
                  Source language
                </label>
                <select
                  id="source-lang"
                  value={local.source_language}
                  onChange={(e) => setLocal({ ...local, source_language: e.target.value })}
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                >
                  {LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code}>{l.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-sm font-medium" htmlFor="target-lang">
                  Target language
                </label>
                <select
                  id="target-lang"
                  value={local.target_language}
                  onChange={(e) => setLocal({ ...local, target_language: e.target.value })}
                  className="mt-1 w-full rounded-md border border-border bg-background px-3 py-2 text-sm"
                >
                  {LANGUAGES.map((l) => (
                    <option key={l.code} value={l.code}>{l.name}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
          </div>

          <div className="flex shrink-0 flex-wrap justify-end gap-2 border-t border-border px-4 py-3">
            <Button variant="outline" onClick={testConnection} disabled={testing}>
              {testing ? "Testing…" : "Test connection"}
            </Button>
            <Button onClick={save}>Save</Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
