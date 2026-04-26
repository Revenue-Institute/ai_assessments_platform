import type { Metadata } from "next";
import { Header } from "./components/header";

export const metadata: Metadata = {
  title: "Dashboard",
  description: "Overview of recent assignments, pending reviews, and integrity flags.",
};

export default function DashboardPage() {
  return (
    <>
      <Header page="Dashboard" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <div className="grid auto-rows-min gap-4 md:grid-cols-3">
          <Card title="Recent assignments" />
          <Card title="Pending reviews" />
          <Card title="Integrity flags" />
        </div>
        <section className="rounded-xl border border-border/50 bg-muted/30 p-6">
          <h2 className="font-medium text-lg">Welcome</h2>
          <p className="mt-1 text-muted-foreground text-sm">
            This is the Revenue Institute Assessments admin console. Real
            dashboard widgets land in Phase 4 once scoring and assignments are
            wired end-to-end. For now, jump into Modules to seed your first
            assessment.
          </p>
        </section>
      </div>
    </>
  );
}

function Card({ title }: { title: string }) {
  return (
    <div className="aspect-video rounded-xl border border-border/50 bg-muted/30 p-4">
      <p className="font-medium text-sm">{title}</p>
      <p className="mt-1 text-muted-foreground text-xs">No data yet.</p>
    </div>
  );
}
