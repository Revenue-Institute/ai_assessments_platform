import { ModeToggle } from "@repo/design-system/components/mode-toggle";
import type { ReactNode } from "react";

export default function UnauthenticatedLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <div className="relative grid min-h-dvh grid-cols-1 lg:grid-cols-2">
      <div className="relative hidden flex-col justify-between bg-emerald-950 p-10 text-emerald-50 lg:flex">
        <div className="font-medium text-lg">Revenue Institute</div>
        <blockquote className="space-y-2 text-emerald-100/90">
          <p>
            Assessments built from the role description. Hands-on, randomized,
            and scored to a rubric. Internal benchmarks and candidate
            screening, in one workflow.
          </p>
        </blockquote>
        <div className="absolute top-4 right-4">
          <ModeToggle />
        </div>
      </div>
      <div className="flex items-center justify-center p-8">
        <div className="w-full max-w-sm">{children}</div>
      </div>
    </div>
  );
}
