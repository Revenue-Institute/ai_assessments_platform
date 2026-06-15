import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
      <div className="flex flex-col gap-2">
        <h2 className="font-semibold text-lg">Page not found</h2>
        <p className="max-w-sm text-muted-foreground text-sm">
          The resource you are looking for does not exist or has been removed.
        </p>
      </div>
      <Link
        className="inline-flex items-center rounded-md bg-primary px-4 py-2 font-medium text-primary-foreground text-sm transition-colors hover:bg-primary/90"
        href="/"
      >
        Go to dashboard
      </Link>
    </div>
  );
}
