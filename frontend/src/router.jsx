import { lazy } from "react";
import { createBrowserRouter } from "react-router";
import AppLayout from "./components/layout/AppLayout";
import { RouteError } from "./components/layout/RouteError";
import { RequireAuth } from "./providers/AuthProvider";
import Login from "./pages/Login";

// Pages load on demand (ADR-02: code-split routes keep first paint fast). AppLayout wraps them in <Suspense>.
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Ingest = lazy(() => import("./pages/Ingest"));
const Review = lazy(() => import("./pages/Review"));
const Materials = lazy(() => import("./pages/Materials"));
const MaterialDetail = lazy(() => import("./pages/MaterialDetail"));
const Search = lazy(() => import("./pages/Search"));
const Graph = lazy(() => import("./pages/Graph"));
const Analytics = lazy(() => import("./pages/Analytics"));
const Audit = lazy(() => import("./pages/Audit"));
const Integrations = lazy(() => import("./pages/Integrations"));
const Settings = lazy(() => import("./pages/Settings"));
const NotFound = lazy(() => import("./pages/NotFound"));

export const router = createBrowserRouter([
  { path: "/login", element: <Login />, errorElement: <RouteError /> },
  {
    path: "/",
    element: <RequireAuth><AppLayout /></RequireAuth>,
    errorElement: <RouteError />,
    children: [
      {
        // A page that crashes shows the error inside the app shell, so the sidebar still works.
        errorElement: <RouteError inline />,
        children: [
          { index: true, element: <Dashboard /> },
          { path: "ingest", element: <Ingest /> },
          { path: "review", element: <Review /> },
          { path: "materials", element: <Materials /> },
          { path: "materials/:nmc", element: <MaterialDetail /> },
          { path: "search", element: <Search /> },
          { path: "graph", element: <Graph /> },
          { path: "graph/:nmc", element: <Graph /> },
          { path: "analytics", element: <Analytics /> },
          { path: "audit", element: <Audit /> },
          { path: "integrations", element: <Integrations /> },
          { path: "settings", element: <Settings /> },
          { path: "*", element: <NotFound /> },
        ],
      },
    ],
  },
]);
