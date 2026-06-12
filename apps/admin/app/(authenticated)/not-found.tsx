import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
      <div className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">Page not found</h2>
        <p className="text-sm text-muted-foreground max-w-sm">
          The resource you are looking for does not exist or has been removed.
        </p>
      </div>
      <Link
        className="inline-flex items-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        href="/"
      >
        Go to dashboard
      </Link>
    </div>
  );
}