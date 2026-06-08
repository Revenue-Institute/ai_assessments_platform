"use client";

import { useState } from "react";

import { SubmitButton } from "@/components/submit-button";

export function AddSubjectForm({
  action,
}: {
  action: (formData: FormData) => Promise<void>;
}) {
  const [type, setType] = useState<"candidate" | "employee">("candidate");

  return (
    <form
      action={action}
      className="grid max-w-2xl grid-cols-1 gap-3 rounded-xl border border-border/50 bg-muted/20 p-4 md:grid-cols-3"
    >
      <label className="space-y-1 md:col-span-1">
        <span className="text-sm">Type</span>
        <select
          className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
          name="type"
          onChange={(e) => setType(e.target.value as "candidate" | "employee")}
          value={type}
        >
          <option value="candidate">candidate</option>
          <option value="employee">employee</option>
        </select>
      </label>
      <label className="space-y-1">
        <span className="text-sm">Full name</span>
        <input
          className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
          name="full_name"
          required
          type="text"
        />
      </label>
      <label className="space-y-1">
        <span className="text-sm">Email</span>
        <input
          className="block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm"
          name="email"
          required
          type="email"
        />
      </label>
      <div className="md:col-span-3">
        <SubmitButton
          className="btn-primary text-sm"
          pendingLabel={`Adding ${type}...`}
        >
          {`Add ${type}`}
        </SubmitButton>
      </div>
    </form>
  );
}
