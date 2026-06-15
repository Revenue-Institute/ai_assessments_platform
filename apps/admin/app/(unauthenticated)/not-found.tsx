import Link from "next/link";

export default function NotFound() {
  return (
    <div className="flex flex-col gap-4 text-center">
      <div className="flex flex-col gap-2">
        <h2 className="font-semibold text-lg">Page not found</h2>
        <p className="text-muted-foreground text-sm">
          The page you are looking for does not exist.
        </p>
      </div>
      <Link
        className="inline-flex items-center justify-center rounded-md bg-primary px-4 py-2 font-medium text-primary-foreground text-sm transition-colors hover:bg-primary/90"
        href="/sign-in"
      >
        Go to sign in
      </Link>
    </div>
  );
}
