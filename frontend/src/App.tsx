import { createBrowserRouter, RouterProvider, useParams } from "react-router";
import { Toaster } from "@/components/ui/sonner";
import { Layout } from "./components/layout/Layout";
import { Overview } from "./pages/Overview";
import { ProjectView } from "./pages/ProjectView";
import { Help } from "./pages/Help";
import { Placeholder } from "./pages/Placeholder";
import { PagesBrowser } from "./pages/PagesBrowser";
import { PageDetail } from "./pages/PageDetail";
import { PageEdit } from "./pages/PageEdit";
import { Sessions } from "./pages/Sessions";
import { SessionDetail } from "./pages/SessionDetail";
import { ActivityCenter } from "./pages/ActivityCenter";
import { ActivityDetail } from "./pages/ActivityDetail";
import { Trash } from "./pages/Trash";
import { Snapshots } from "./pages/Snapshots";
import { Suggestions } from "./pages/Suggestions";
import { Health } from "./pages/Health";
import { LostSessions } from "./pages/LostSessions";
import { DeadLetter } from "./pages/DeadLetter";
import { DeadLetterDetail } from "./pages/DeadLetterDetail";

// react-router v7 splats must be path-final, so a literal `pages/*/edit` route
// cannot exist. Both PageDetail and PageEdit share `pages/*`; this switch
// dispatches based on whether the splat ends in `/edit`.
function PagesRouteSwitch() {
  const { "*": rest } = useParams<{ "*": string }>();
  return rest?.endsWith("/edit") ? <PageEdit /> : <PageDetail />;
}

const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout />,
    children: [
      { index: true, element: <Overview /> },
      { path: "onboarding", element: <Placeholder section="Onboarding" plan="#14d" /> },
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
          { path: "queue", element: <Placeholder section="Queue" plan="#14b" /> },
          { path: "settings", element: <Placeholder section="Settings" plan="#14c" /> },
        ],
      },
      { path: "lost-sessions", element: <LostSessions /> },
      { path: "dead-letter", element: <DeadLetter /> },
      { path: "dead-letter/:jobId", element: <DeadLetterDetail /> },
      { path: "help", element: <Help /> },
      { path: "metrics", element: <Placeholder section="Metrics" plan="#14d" /> },
      { path: "settings/global", element: <Placeholder section="Global Settings" plan="#14c" /> },
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
