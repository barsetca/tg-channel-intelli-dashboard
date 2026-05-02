function getBaseUrl(): string {
  if (typeof window === "undefined" && process.env.API_URL) {
    return process.env.API_URL;
  }
  return process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";
}

export type HealthResponse = {
  status: string;
  environment: string;
};

export async function fetchHealth(): Promise<HealthResponse> {
  const res = await fetch(`${getBaseUrl()}/api/v1/health`, { next: { revalidate: 0 } });
  if (!res.ok) {
    throw new Error(`Health check failed: ${res.status}`);
  }
  return res.json() as Promise<HealthResponse>;
}
