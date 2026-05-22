import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/settings")({
  component: SettingsPage,
});

function SettingsPage() {
  return (
    <div className="p-4">
      <h1 className="text-xl font-semibold mb-4">Settings</h1>
      {/* user preferences */}
    </div>
  );
}
