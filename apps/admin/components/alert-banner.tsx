import type { ReactNode } from "react";

const STYLES = {
  error: "border-destructive/50 bg-destructive/15 text-destructive",
  success: "border-primary/50 bg-primary/15 text-primary",
};

export function AlertBanner({
  children,
  className,
  variant = "error",
}: {
  children: ReactNode;
  className?: string;
  variant?: "error" | "success";
}) {
  if (!children) return null;
  return (
    <p
      className={`rounded border px-3 py-2 text-sm ${STYLES[variant]}${className ? ` ${className}` : ""}`}
      role={variant === "error" ? "alert" : "status"}
    >
      {children}
    </p>
  );
}
