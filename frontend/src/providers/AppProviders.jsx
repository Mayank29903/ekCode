import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router";
import { Toaster } from "sonner";
import { MotionConfig } from "motion/react";
import { AuthProvider } from "./AuthProvider";
import { router } from "../router";
import { useTheme } from "../hooks/useTheme";

// Retrying cannot fix "not signed in", "not allowed", "not found", "conflict" or "invalid": only network/server errors.
const NO_RETRY = new Set([400, 401, 403, 404, 409, 410, 422]);

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 15_000, refetchOnWindowFocus: false, retry: (n, err) => !NO_RETRY.has(err?.status) && n < 2 },
  },
});

function ThemedToaster() {
  const { theme } = useTheme();
  return <Toaster theme={theme} position="bottom-right" richColors closeButton toastOptions={{ className: "!rounded-2xl" }} />;
}

export default function AppProviders() {
  return (
    <QueryClientProvider client={queryClient}>
      <MotionConfig reducedMotion="user">
        <AuthProvider>
          <RouterProvider router={router} />
          <ThemedToaster />
        </AuthProvider>
      </MotionConfig>
    </QueryClientProvider>
  );
}
