import { PlaceholderPage } from "../../components/placeholder-page";

export default function SettingsUsersPage() {
  return (
    <PlaceholderPage
      description="Manage internal users (admin / reviewer / viewer). Until the management UI lands, provision users in the Supabase dashboard."
      page="Users"
      pages={["Settings"]}
      phase="Phase 5"
    />
  );
}
