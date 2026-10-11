const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: "RIDER" | "DRIVER" | "ADMIN";
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user_id: string;
  role: "RIDER" | "DRIVER" | "ADMIN";
}

export interface FareEstimate {
  distance_km: number;
  estimated_duration_minutes: number;
  base_fare: number;
  distance_fare: number;
  time_fare: number;
  total_fare: number;
  currency: string;
}

export interface Ride {
  id: string;
  rider_id: string;
  driver_id?: string;
  status: "REQUESTED" | "MATCHING" | "ACCEPTED" | "ARRIVED" | "IN_PROGRESS" | "COMPLETED" | "CANCELLED";
  pickup_latitude: number;
  pickup_longitude: number;
  pickup_address: string;
  dropoff_latitude: number;
  dropoff_longitude: number;
  dropoff_address: string;
  estimated_fare: number;
  final_fare?: number;
  currency: string;
  requested_at: string;
}

export const api = {
  async register(data: any): Promise<User> {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Registration failed");
    return res.json();
  },

  async login(email: string, password: string): Promise<AuthResponse> {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Login failed");
    return res.json();
  },

  async getMe(token: string): Promise<User> {
    const res = await fetch(`${API_BASE}/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error("Failed to get profile");
    return res.json();
  },

  async estimateFare(pickup: { latitude: number; longitude: number }, dropoff: { latitude: number; longitude: number }): Promise<FareEstimate> {
    const res = await fetch(`${API_BASE}/rides/estimate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pickup, dropoff }),
    });
    if (!res.ok) throw new Error("Failed to estimate fare");
    return res.json();
  },

  async createRide(token: string, payload: any): Promise<Ride> {
    const res = await fetch(`${API_BASE}/rides`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to create ride");
    return res.json();
  },

  async getRide(token: string, rideId: string): Promise<Ride> {
    const res = await fetch(`${API_BASE}/rides/${rideId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error("Failed to fetch ride");
    return res.json();
  },

  async getMyRides(token: string): Promise<Ride[]> {
    const res = await fetch(`${API_BASE}/rides/me/history`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error("Failed to fetch rides");
    return res.json();
  },

  async acceptRide(token: string, rideId: string): Promise<Ride> {
    const res = await fetch(`${API_BASE}/rides/${rideId}/accept`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error((await res.json()).detail || "Failed to accept ride");
    return res.json();
  },

  async arriveRide(token: string, rideId: string): Promise<Ride> {
    const res = await fetch(`${API_BASE}/rides/${rideId}/arrive`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error("Failed to update status to arrived");
    return res.json();
  },

  async startRide(token: string, rideId: string): Promise<Ride> {
    const res = await fetch(`${API_BASE}/rides/${rideId}/start`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error("Failed to start ride");
    return res.json();
  },

  async completeRide(token: string, rideId: string): Promise<Ride> {
    const res = await fetch(`${API_BASE}/rides/${rideId}/complete`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!res.ok) throw new Error("Failed to complete ride");
    return res.json();
  },

  async cancelRide(token: string, rideId: string, reason?: string): Promise<Ride> {
    const res = await fetch(`${API_BASE}/rides/${rideId}/cancel`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ reason: reason || "User cancelled" }),
    });
    if (!res.ok) throw new Error("Failed to cancel ride");
    return res.json();
  },

  async setDriverStatus(token: string, status: "ONLINE" | "OFFLINE"): Promise<any> {
    const res = await fetch(`${API_BASE}/drivers/status`, {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ status }),
    });
    if (!res.ok) throw new Error("Failed to update driver status");
    return res.json();
  },
};
