import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col gap-4 text-center">
      <div className="flex flex-col gap-2">
        <h2 className="text-lg font-semibold">Page not found</h2>
        <p className="text-sm text-muted-foreground">
          The page you are looking for does not exist.
        </p>
      </div>
      <Link
        className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90 transition-colors"
        href="/sign-in"
      >
        Go to sign in
      </Link>
    </div>
  );
}
