"use client";

import Editor from "@monaco-editor/react";

const SUPPORTED_MONACO_LANGS = new Set([
  "python",
  "javascript",
  "typescript",
  "sql",
  "shell",
]);

const monacoLanguage = (lang: string | undefined): string => {
  if (!lang) return "python";
  if (lang === "bash") return "shell";
  if (SUPPORTED_MONACO_LANGS.has(lang)) return lang;
  return "plaintext";
};

/** Read-only Monaco view for the admin preview. Same editor candidates
 * see when taking the assessment, just disabled (no Run / Test buttons,
 * no `data-allow-paste` zone, no integrity wiring). Reviewers get the
 * exact code-question look without spinning up an attempt. */
export function CodePreviewMonaco({
  code,
  language,
  height = "260px",
}: {
  code: string;
  language: string | undefined;
  height?: string;
}) {
  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <Editor
        defaultLanguage={monacoLanguage(language)}
        height={height}
        options={{
          minimap: { enabled: false },
          readOnly: true,
          domReadOnly: true,
          fontSize: 13,
          scrollBeyondLastLine: false,
          tabSize: 4,
          renderLineHighlight: "none",
        }}
        theme="vs-dark"
        value={code || "# starter empty"}
      />
    </div>
  );
}
