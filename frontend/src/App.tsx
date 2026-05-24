import { lazy, Suspense } from "react";
import { createBrowserRouter, Navigate, RouterProvider, useParams } from "react-router";
import { Toaster } from "@/components/ui/sonner";
import { Skeleton } from "@/components/ui/skeleton";
import { Layout } from "./components/layout/Layout";
import { Overview } from "./pages/Overview";
import { ProjectView } from "./pages/ProjectView";
import { PagesBrowser } from "./pages/PagesBrowser";
import { PageDetail } from "./pages/PageDetail";
import { PageEdit } from "./pages/PageEdit";
import { Sessions } from "./pages/Sessions";
import { SessionDetail } from "./pages/SessionDetail";
import { Queue } from "./pages/Queue";
import { ActivityCenter } from "./pages/ActivityCenter";
import { ActivityDetail } from "./pages/ActivityDetail";
import { Trash } from "./pages/Trash";
import { Snapshots } from "./pages/Snapshots";
import { Suggestions } from "./pages/Suggestions";
import { Health } from "./pages/Health";
import { LostSessions } from "./pages/LostSessions";
import IgnoredSessions from "./pages/IgnoredSessions";
import { DeadLetter } from "./pages/DeadLetter";
import { DeadLetterDetail } from "./pages/DeadLetterDetail";
import { OnboardingWelcome } from "./pages/OnboardingWelcome";
import { OnboardingAdvanced } from "./pages/OnboardingAdvanced";
import { ProjectSettings } from "./pages/ProjectSettings";
import { GlobalSettings } from "./pages/GlobalSettings";
import { Diagnostics } from "./pages/Diagnostics";

const Help = lazy(() => import("./pages/Help"));
const Metrics = lazy(() => import("./pages/Metrics"));
const Lint = lazy(() => import("./pages/Lint"));

// react-router v7 splats must be path-final, so a literal `pages/*/edit` route
// cannot exist. Both PageDetail and PageEdit share `pages/*`; this switch
// dispatches based on whether the splat ends in `/edit`.
function PagesRouteSwitch() {
  const { "*": rest } = useParams<{ "*": string }>();
  return rest?.endsWith("/edit") ? <PageEdit /> : <PageDetail />;
}

function LostSessionsProjectRedirect() {
  const { name } = useParams<{ name: string }>();
  return (
    <Navigate
      to={`/lost-sessions${name ? `?project=${encodeURIComponent(name)}` : ""}`}
      replace
    />
  );
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Overview /> },
      { path: "onboarding", element: <OnboardingWelcome /> },
      { path: "onboarding/advanced", element: <OnboardingAdvanced /> },
      {
        path: "project/:name",
        children: [
          { index: true, element: <ProjectView /> },
          { path: "pages", element: <PagesBrowser /> },
          { path: "pages/*", element: <PagesRouteSwitch /> },
          { path: "sessions", element: <Sessions /> },
          { path: "sessions/:sid", element: <SessionDetail /> },
          { path: "activity", element: <ActivityCenter /> },
          { path: "activity/:opId", element: <ActivityDetail /> },
          { path: "suggestions", element: <Suggestions /> },
          { path: "trash", element: <Trash /> },
          { path: "snapshots", element: <Snapshots /> },
          { path: "health", element: <Health /> },
          { path: "queue", element: <Queue /> },
          { path: "lost-sessions", element: <LostSessionsProjectRedirect /> },
          {
            path: "lint",
            element: (
              <Suspense fallback={<Skeleton className="h-64" />}>
                <Lint />
              </Suspense>
            ),
          },
          { path: "settings", element: <ProjectSettings /> },
        ],
      },
      { path: "lost-sessions", element: <LostSessions /> },
      { path: "lost-sessions/ignored", element: <IgnoredSessions /> },
      { path: "dead-letter", element: <DeadLetter /> },
      { path: "dead-letter/:jobId", element: <DeadLetterDetail /> },
      { path: "help", element: <Suspense fallback={<Skeleton className="h-64" />}><Help /></Suspense> },
      { path: "metrics", element: <Suspense fallback={<Skeleton className="h-64" />}><Metrics /></Suspense> },
      { path: "settings/global", element: <GlobalSettings /> },
      { path: "diagnostics", element: <Diagnostics /> },
    ],
  },
]);

export default function App() {
  return (
    <>
      <RouterProvider router={router} />
      <Toaster richColors position="bottom-right" />
    </>
  );
}
