import { useEffect, useState } from "react";
import { fetchBackendHealth, fetchMcpStatus } from "../api/health";

export type DashboardStatus = {
  backendOnline: boolean;
  mcpAvailable: boolean;
  loading: boolean;
};

export function useHealth(): DashboardStatus {
  const [state, setState] = useState<DashboardStatus>({
    backendOnline: false,
    mcpAvailable: false,
    loading: true,
  });

  useEffect(() => {
    let cancelled = false;

    async function load() {
      const [healthResult, mcpResult] = await Promise.allSettled([
        fetchBackendHealth(),
        fetchMcpStatus(),
      ]);

      if (cancelled) {
        return;
      }

      setState({
        backendOnline: healthResult.status === "fulfilled" && healthResult.value.status === "ok",
        mcpAvailable: mcpResult.status === "fulfilled" && mcpResult.value.status === "available",
        loading: false,
      });
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}