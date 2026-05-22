import { createFileRoute, Link } from "@tanstack/react-router";

export const Route = createFileRoute("/spots")({
  component: SpotsPage,
});

interface Spot {
  id: string;
  name: string;
  lat: number;
  lon: number;
}

function useSpots(): Spot[] {
  return JSON.parse(localStorage.getItem("spots") ?? "[]");
}

function SpotsPage() {
  const spots = useSpots();

  return (
    <div className="p-4 space-y-2">
      {spots.length === 0 && (
        <p className="text-muted-foreground">No saved spots. Add one from the map.</p>
      )}
      {spots.map((spot) => (
        <Link
          key={spot.id}
          to="/forecast"
          search={{ lat: spot.lat, lon: spot.lon, name: spot.name }}
          className="block p-4 rounded-lg border hover:bg-muted transition-colors"
        >
          <p className="font-medium">{spot.name}</p>
          <p className="text-sm text-muted-foreground">
            {spot.lat.toFixed(4)}, {spot.lon.toFixed(4)}
          </p>
        </Link>
      ))}
    </div>
  );
}
