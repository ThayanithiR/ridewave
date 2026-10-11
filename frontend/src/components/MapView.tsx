"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import "leaflet/dist/leaflet.css";

interface MapViewProps {
  pickup?: { lat: number; lng: number };
  dropoff?: { lat: number; lng: number };
  driverLocation?: { lat: number; lng: number };
  onMapClick?: (coords: { lat: number; lng: number }) => void;
}

const DynamicMap = dynamic(
  async () => {
    const L = await import("leaflet");
    const { MapContainer, TileLayer, Marker, Popup, useMapEvents } = await import("react-leaflet");

    // Fix default marker icon issues with webpack / Next.js
    const DefaultIcon = L.icon({
      iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
      shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
      iconSize: [25, 41],
      iconAnchor: [12, 41],
    });
    L.Marker.prototype.options.icon = DefaultIcon;

    function ClickHandler({ onClick }: { onClick?: (coords: { lat: number; lng: number }) => void }) {
      useMapEvents({
        click(e) {
          if (onClick) {
            onClick({ lat: e.latlng.lat, lng: e.latlng.lng });
          }
        },
      });
      return null;
    }

    return function MapComponent({ pickup, dropoff, driverLocation, onMapClick }: MapViewProps) {
      const center = pickup ? [pickup.lat, pickup.lng] : [40.7128, -74.006];

      return (
        <MapContainer
          center={center as [number, number]}
          zoom={13}
          style={{ height: "100%", width: "100%", borderRadius: "0.75rem" }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <ClickHandler onClick={onMapClick} />
          {pickup && (
            <Marker position={[pickup.lat, pickup.lng]}>
              <Popup>Pickup Location</Popup>
            </Marker>
          )}
          {dropoff && (
            <Marker position={[dropoff.lat, dropoff.lng]}>
              <Popup>Dropoff Destination</Popup>
            </Marker>
          )}
          {driverLocation && (
            <Marker position={[driverLocation.lat, driverLocation.lng]}>
              <Popup>Assigned Driver</Popup>
            </Marker>
          )}
        </MapContainer>
      );
    };
  },
  { ssr: false, loading: () => <div className="h-full w-full bg-slate-100 flex items-center justify-center text-slate-400">Loading OpenStreetMap...</div> }
);

export default function MapView(props: MapViewProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) return <div className="h-full w-full bg-slate-100 rounded-xl" />;
  return <DynamicMap {...props} />;
}
