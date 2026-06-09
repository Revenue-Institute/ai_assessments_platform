import type { ComponentPropsWithoutRef } from "react";

const VARIANTS = {
  default:
    "rounded border border-border/40 px-2 py-0.5 text-xs hover:bg-muted disabled:opacity-40",
  primary:
    "rounded border border-primary/40 bg-primary/10 px-2 py-0.5 text-primary text-xs hover:bg-primary/20 disabled:opacity-40",
  destructive:
    "rounded border border-destructive/40 px-2 py-0.5 text-destructive text-xs hover:bg-destructive/15 disabled:opacity-40",
};

export function ActionButton({
  variant = "default",
  className,
  ...props
}: ComponentPropsWithoutRef<"button"> & {
  variant?: keyof typeof VARIANTS;
}) {
  return (
    <button
      className={className ? `${VARIANTS[variant]} ${className}` : VARIANTS[variant]}
      type="button"
      {...props}
    />
  );
}
