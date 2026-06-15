import type { Metadata } from "next";

import { PlaceholderPage } from "../../components/placeholder-page";

export const metadata: Metadata = { title: "API Settings" };

export const dynamic = "force-dynamic";

export default function SettingsApiPage() {
  return (
    <PlaceholderPage
      description="Coming after v1."
      page="API keys for integrations"
      pages={["Settings"]}
      phase="Roadmap"
    />
  );
}
