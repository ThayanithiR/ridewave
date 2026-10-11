"use client";

import { useState, useEffect } from "react";
import { api, User, Ride, FareEstimate } from "@/lib/api";
import MapView from "@/components/MapView";
import { Car, Navigation, MapPin, CheckCircle, Clock, AlertCircle } from "lucide-react";

export default function Home() {
  const [token, setToken] = useState<string>("");
  const [user, setUser] = useState<User | null>(null);

  // Auth inputs
  const [email, setEmail] = useState("rider@example.com");
  const [password, setPassword] = useState("password123");
  const [role, setRole] = useState<"RIDER" | "DRIVER">("RIDER");
  const [fullName, setFullName] = useState("Alex Rider");

  // Ride booking inputs
  const [pickupAddress, setPickupAddress] = useState("Times Square, NYC");
  const [pickupCoords, setPickupCoords] = useState({ lat: 40.7580, lng: -73.9855 });
  const [dropoffAddress, setDropoffAddress] = useState("Empire State Building, NYC");
  const [dropoffCoords, setDropoffCoords] = useState({ lat: 40.7484, lng: -73.9857 });

  const [estimate, setEstimate] = useState<FareEstimate | null>(null);
  const [activeRide, setActiveRide] = useState<Ride | null>(null);
  const [history, setHistory] = useState<Ride[]>([]);
  const [driverStatus, setDriverStatus] = useState<"ONLINE" | "OFFLINE">("OFFLINE");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Auto-fetch profile and active rides
  useEffect(() => {
    if (!token) return;
    api.getMe(token).then(setUser).catch(() => setToken(""));
    loadHistory();
  }, [token]);

  const loadHistory = async () => {
    if (!token) return;
    try {
      const rides = await api.getMyRides(token);
      setHistory(rides);
      const ongoing = rides.find((r) => !["COMPLETED", "CANCELLED"].includes(r.status));
      if (ongoing) setActiveRide(ongoing);
    } catch (e: any) {
      console.error(e);
    }
  };

  const handleAuth = async (isLogin: boolean) => {
    setError(null);
    setLoading(true);
    try {
      if (isLogin) {
        const res = await api.login(email, password);
        setToken(res.access_token);
      } else {
        await api.register({ email, password, full_name: fullName, role });
        const res = await api.login(email, password);
        setToken(res.access_token);
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleEstimate = async () => {
    setError(null);
    try {
      const est = await api.estimateFare(
        { latitude: pickupCoords.lat, longitude: pickupCoords.lng },
        { latitude: dropoffCoords.lat, longitude: dropoffCoords.lng }
      );
      setEstimate(est);
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleRequestRide = async () => {
    if (!token) return;
    setError(null);
    setLoading(true);
    try {
      const ride = await api.createRide(token, {
        pickup_latitude: pickupCoords.lat,
        pickup_longitude: pickupCoords.lng,
        pickup_address: pickupAddress,
        dropoff_latitude: dropoffCoords.lat,
        dropoff_longitude: dropoffCoords.lng,
        dropoff_address: dropoffAddress,
      });
      setActiveRide(ride);
      loadHistory();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDriverAction = async (action: "accept" | "arrive" | "start" | "complete") => {
    if (!token || !activeRide) return;
    setLoading(true);
    try {
      let updated: Ride;
      if (action === "accept") updated = await api.acceptRide(token, activeRide.id);
      else if (action === "arrive") updated = await api.arriveRide(token, activeRide.id);
      else if (action === "start") updated = await api.startRide(token, activeRide.id);
      else updated = await api.completeRide(token, activeRide.id);

      setActiveRide(updated.status === "COMPLETED" ? null : updated);
      loadHistory();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCancelRide = async () => {
    if (!token || !activeRide) return;
    try {
      await api.cancelRide(token, activeRide.id);
      setActiveRide(null);
      loadHistory();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const toggleDriverOnline = async () => {
    if (!token) return;
    const nextStatus = driverStatus === "ONLINE" ? "OFFLINE" : "ONLINE";
    try {
      await api.setDriverStatus(token, nextStatus);
      setDriverStatus(nextStatus);
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="min-h-screen bg-slate-50 flex flex-col font-sans text-slate-900">
      {/* Header */}
      <header className="border-b bg-white px-6 py-4 flex items-center justify-between shadow-sm">
        <div className="flex items-center gap-2">
          <div className="h-9 w-9 bg-black text-white rounded-lg flex items-center justify-center font-bold text-lg">
            R
          </div>
          <span className="text-xl font-bold tracking-tight">RideWave</span>
          <span className="text-xs bg-emerald-100 text-emerald-800 font-semibold px-2 py-0.5 rounded-full">
            Dev Mode
          </span>
        </div>
        {user ? (
          <div className="flex items-center gap-4">
            <span className="text-sm font-medium text-slate-600">
              {user.full_name} ({user.role})
            </span>
            <button
              onClick={() => { setToken(""); setUser(null); setActiveRide(null); }}
              className="text-xs font-semibold text-rose-600 hover:text-rose-700 border border-rose-200 px-3 py-1.5 rounded-md"
            >
              Sign out
            </button>
          </div>
        ) : (
          <div className="text-xs text-slate-500 font-medium">Please sign in to book or drive</div>
        )}
      </header>

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Side: Controls & Workflows */}
        <div className="lg:col-span-5 flex flex-col gap-6">
          {error && (
            <div className="bg-rose-50 border border-rose-200 text-rose-700 px-4 py-3 rounded-xl flex items-start gap-3 text-sm">
              <AlertCircle className="h-5 w-5 shrink-0 mt-0.5" />
              <span>{error}</span>
            </div>
          )}

          {!user ? (
            /* Authentication Panel */
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
              <h2 className="text-lg font-bold mb-4">Welcome to RideWave</h2>
              <div className="flex gap-2 mb-4">
                <button
                  onClick={() => setRole("RIDER")}
                  className={`flex-1 py-2 text-sm font-semibold rounded-lg border ${
                    role === "RIDER" ? "bg-black text-white border-black" : "bg-white text-slate-700"
                  }`}
                >
                  Rider
                </button>
                <button
                  onClick={() => setRole("DRIVER")}
                  className={`flex-1 py-2 text-sm font-semibold rounded-lg border ${
                    role === "DRIVER" ? "bg-black text-white border-black" : "bg-white text-slate-700"
                  }`}
                >
                  Driver
                </button>
              </div>

              <div className="space-y-3">
                <div>
                  <label className="text-xs font-semibold text-slate-600">Full Name</label>
                  <input
                    type="text"
                    value={fullName}
                    onChange={(e) => setFullName(e.target.value)}
                    className="w-full mt-1 px-3 py-2 border rounded-lg text-sm focus:outline-black"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-600">Email</label>
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="w-full mt-1 px-3 py-2 border rounded-lg text-sm focus:outline-black"
                  />
                </div>
                <div>
                  <label className="text-xs font-semibold text-slate-600">Password</label>
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="w-full mt-1 px-3 py-2 border rounded-lg text-sm focus:outline-black"
                  />
                </div>

                <div className="flex gap-3 pt-2">
                  <button
                    disabled={loading}
                    onClick={() => handleAuth(true)}
                    className="flex-1 bg-black text-white font-semibold py-2.5 rounded-lg text-sm hover:bg-slate-800 disabled:opacity-50"
                  >
                    Log In
                  </button>
                  <button
                    disabled={loading}
                    onClick={() => handleAuth(false)}
                    className="flex-1 bg-slate-100 text-slate-900 font-semibold py-2.5 rounded-lg text-sm hover:bg-slate-200 border border-slate-300 disabled:opacity-50"
                  >
                    Register
                  </button>
                </div>
              </div>
            </div>
          ) : user.role === "RIDER" ? (
            /* Rider Interface */
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-5">
              <h2 className="text-lg font-bold flex items-center gap-2">
                <Car className="h-5 w-5 text-indigo-600" /> Book a Ride
              </h2>

              {!activeRide ? (
                <>
                  <div className="space-y-3">
                    <div>
                      <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                        <MapPin className="h-3.5 w-3.5 text-emerald-600" /> Pickup
                      </label>
                      <input
                        type="text"
                        value={pickupAddress}
                        onChange={(e) => setPickupAddress(e.target.value)}
                        className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                      />
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-slate-500 uppercase tracking-wider flex items-center gap-1.5">
                        <Navigation className="h-3.5 w-3.5 text-rose-600" /> Dropoff
                      </label>
                      <input
                        type="text"
                        value={dropoffAddress}
                        onChange={(e) => setDropoffAddress(e.target.value)}
                        className="w-full mt-1 px-3 py-2 border rounded-lg text-sm"
                      />
                    </div>
                  </div>

                  <div className="flex gap-3">
                    <button
                      onClick={handleEstimate}
                      className="flex-1 bg-slate-100 font-semibold text-slate-800 py-2.5 rounded-lg text-sm hover:bg-slate-200 border"
                    >
                      Get Estimate
                    </button>
                    <button
                      onClick={handleRequestRide}
                      disabled={loading}
                      className="flex-1 bg-black text-white font-semibold py-2.5 rounded-lg text-sm hover:bg-slate-800"
                    >
                      Request Ride
                    </button>
                  </div>

                  {estimate && (
                    <div className="p-4 bg-slate-50 rounded-xl border border-slate-200 space-y-2">
                      <div className="flex justify-between items-center">
                        <span className="text-sm font-semibold">Estimated Fare</span>
                        <span className="text-xl font-extrabold text-indigo-600">
                          ${estimate.total_fare.toFixed(2)}
                        </span>
                      </div>
                      <div className="text-xs text-slate-500 flex justify-between">
                        <span>Distance: {estimate.distance_km} km</span>
                        <span>Duration: ~{estimate.estimated_duration_minutes} mins</span>
                      </div>
                    </div>
                  )}
                </>
              ) : (
                /* Active Ride View */
                <div className="p-5 bg-indigo-50/50 border border-indigo-100 rounded-2xl space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-xs font-bold uppercase tracking-wider text-indigo-800 bg-indigo-100 px-2.5 py-1 rounded-full">
                      Status: {activeRide.status}
                    </span>
                    <span className="text-lg font-bold">${activeRide.estimated_fare.toFixed(2)}</span>
                  </div>

                  <div className="text-sm space-y-1">
                    <p className="text-slate-600"><strong>Pickup:</strong> {activeRide.pickup_address}</p>
                    <p className="text-slate-600"><strong>Dropoff:</strong> {activeRide.dropoff_address}</p>
                  </div>

                  {activeRide.status === "REQUESTED" && (
                    <p className="text-xs text-slate-500 animate-pulse">Searching for nearby available drivers...</p>
                  )}

                  <button
                    onClick={handleCancelRide}
                    className="w-full py-2 bg-rose-50 hover:bg-rose-100 text-rose-700 text-sm font-semibold rounded-lg border border-rose-200"
                  >
                    Cancel Ride
                  </button>
                </div>
              )}
            </div>
          ) : (
            /* Driver Interface */
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-5">
              <div className="flex justify-between items-center">
                <h2 className="text-lg font-bold">Driver Terminal</h2>
                <button
                  onClick={toggleDriverOnline}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition ${
                    driverStatus === "ONLINE"
                      ? "bg-emerald-500 text-white border-emerald-600"
                      : "bg-slate-200 text-slate-700 border-slate-300"
                  }`}
                >
                  {driverStatus === "ONLINE" ? "ONLINE" : "GO ONLINE"}
                </button>
              </div>

              {activeRide ? (
                <div className="p-5 bg-amber-50/60 border border-amber-200 rounded-2xl space-y-4">
                  <div className="flex justify-between items-center">
                    <span className="text-xs font-bold uppercase text-amber-800 bg-amber-100 px-2.5 py-1 rounded-full">
                      Ride Status: {activeRide.status}
                    </span>
                    <span className="font-extrabold text-slate-900">${activeRide.estimated_fare.toFixed(2)}</span>
                  </div>

                  <div className="text-xs space-y-1">
                    <p><strong>Rider Pickup:</strong> {activeRide.pickup_address}</p>
                    <p><strong>Destination:</strong> {activeRide.dropoff_address}</p>
                  </div>

                  <div className="pt-2">
                    {activeRide.status === "REQUESTED" && (
                      <button
                        onClick={() => handleDriverAction("accept")}
                        className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-lg text-sm"
                      >
                        Accept Ride Request
                      </button>
                    )}
                    {activeRide.status === "ACCEPTED" && (
                      <button
                        onClick={() => handleDriverAction("arrive")}
                        className="w-full py-2.5 bg-blue-600 hover:bg-blue-700 text-white font-semibold rounded-lg text-sm"
                      >
                        Arrived at Pickup Location
                      </button>
                    )}
                    {activeRide.status === "ARRIVED" && (
                      <button
                        onClick={() => handleDriverAction("start")}
                        className="w-full py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white font-semibold rounded-lg text-sm"
                      >
                        Start Trip (Rider Onboard)
                      </button>
                    )}
                    {activeRide.status === "IN_PROGRESS" && (
                      <button
                        onClick={() => handleDriverAction("complete")}
                        className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-lg text-sm"
                      >
                        Complete Trip & Collect Fare
                      </button>
                    )}
                  </div>
                </div>
              ) : (
                <div className="p-8 text-center text-slate-400 border border-dashed rounded-xl">
                  {driverStatus === "ONLINE"
                    ? "Standing by for ride dispatches..."
                    : "Go ONLINE to receive nearby rider bookings."}
                </div>
              )}
            </div>
          )}

          {/* Ride History */}
          {user && history.length > 0 && (
            <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
              <h3 className="text-sm font-bold text-slate-700 uppercase tracking-wider mb-3">
                Recent Trips
              </h3>
              <div className="space-y-2.5 max-h-52 overflow-y-auto">
                {history.map((r) => (
                  <div key={r.id} className="p-3 bg-slate-50 border rounded-lg flex justify-between items-center text-xs">
                    <div>
                      <p className="font-semibold text-slate-800">{r.pickup_address} → {r.dropoff_address}</p>
                      <p className="text-slate-400">{new Date(r.requested_at).toLocaleTimeString()} • {r.status}</p>
                    </div>
                    <span className="font-bold text-slate-900">${r.estimated_fare.toFixed(2)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right Side: Interactive OpenStreetMap */}
        <div className="lg:col-span-7 h-[650px] bg-white p-2 rounded-2xl shadow-sm border border-slate-200 flex flex-col">
          <div className="px-3 py-2 border-b flex justify-between items-center text-xs text-slate-500">
            <span>OpenStreetMap • Click to pick locations</span>
            <span className="font-semibold text-slate-700">Live Geo View</span>
          </div>
          <div className="flex-1 mt-2 rounded-xl overflow-hidden relative">
            <MapView
              pickup={pickupCoords}
              dropoff={dropoffCoords}
              onMapClick={(coords) => {
                setPickupCoords(coords);
                setPickupAddress(`Selected: ${coords.lat.toFixed(4)}, ${coords.lng.toFixed(4)}`);
              }}
            />
          </div>
        </div>
      </main>
    </div>
  );
}
