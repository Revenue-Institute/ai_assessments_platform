import type { ComponentPropsWithoutRef, ReactNode } from "react";

const INPUT_BASE =
  "block w-full rounded border border-border/60 bg-background px-3 py-2 text-sm";

export function FormField({
  label,
  className,
  children,
}: {
  label: ReactNode;
  className?: string;
  children: ReactNode;
}) {
  return (
    <label className={`space-y-1${className ? ` ${className}` : ""}`}>
      <span className="text-sm">{label}</span>
      {children}
    </label>
  );
}

export function FormInput({
  className,
  ...props
}: ComponentPropsWithoutRef<"input">) {
  return (
    <input className={className ? `${INPUT_BASE} ${className}` : INPUT_BASE} {...props} />
  );
}

export function FormTextarea({
  className,
  ...props
}: ComponentPropsWithoutRef<"textarea">) {
  return (
    <textarea
      className={className ? `${INPUT_BASE} ${className}` : INPUT_BASE}
      {...props}
    />
  );
}

export function FormSelect({
  className,
  children,
  ...props
}: ComponentPropsWithoutRef<"select">) {
  return (
    <select className={className ? `${INPUT_BASE} ${className}` : INPUT_BASE} {...props}>
      {children}
    </select>
  );
}
