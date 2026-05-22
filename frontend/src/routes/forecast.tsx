import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/forecast")({
  validateSearch: (search: Record<string, unknown>) => ({
    lat: Number(search.lat),
    lon: Number(search.lon),
    name: typeof search.name === "string" ? search.name : undefined,
  }),
  component: ForecastPage,
});

function ForecastPage() {
  const { lat, lon, name } = Route.useSearch();

  return (
    <div className="p-4">
      <h1 className="text-xl font-semibold mb-1">{name ?? "Forecast"}</h1>
      <p className="text-sm text-muted-foreground mb-4">
        {lat.toFixed(4)}, {lon.toFixed(4)}
      </p>
      {/* forecast model output goes here */}
    </div>
  );
}
