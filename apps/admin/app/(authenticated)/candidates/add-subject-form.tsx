"use client";

import { useState } from "react";

import { FormField, FormInput, FormSelect } from "@/components/form-fields";
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
      <FormField className="md:col-span-1" label="Type">
        <FormSelect
          name="type"
          onChange={(e) => setType(e.target.value as "candidate" | "employee")}
          value={type}
        >
          <option value="candidate">candidate</option>
          <option value="employee">employee</option>
        </FormSelect>
      </FormField>
      <FormField label="Full name">
        <FormInput name="full_name" required type="text" />
      </FormField>
      <FormField label="Email">
        <FormInput name="email" required type="email" />
      </FormField>
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
