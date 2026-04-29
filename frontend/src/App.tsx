import { createBrowserRouter, RouterProvider } from "react-router";
import { Layout } from "./components/layout/Layout";
import { Overview } from "./pages/Overview";
import { ProjectView } from "./pages/ProjectView";
import { Help } from "./pages/Help";
import { Placeholder } from "./pages/Placeholder";
import { Sessions } from "./pages/Sessions";
import { SessionDetail } from "./pages/SessionDetail";
import { ActivityCenter } from "./pages/ActivityCenter";
import { ActivityDetail } from "./pages/ActivityDetail";

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
          { path: "pages", element: <Placeholder section="Pages" plan="#14b" /> },
          { path: "pages/:pageId", element: <Placeholder section="Page detail" plan="#14b" /> },
          { path: "sessions", element: <Sessions /> },
          { path: "sessions/:sid", element: <SessionDetail /> },
          { path: "activity", element: <ActivityCenter /> },
          { path: "activity/:opId", element: <ActivityDetail /> },
          { path: "suggestions", element: <Placeholder section="Suggestions" plan="#14b" /> },
          { path: "trash", element: <Placeholder section="Trash" plan="#14b" /> },
          { path: "snapshots", element: <Placeholder section="Snapshots" plan="#14b" /> },
          { path: "health", element: <Placeholder section="Health" plan="#14b" /> },
          { path: "queue", element: <Placeholder section="Queue" plan="#14b" /> },
          { path: "settings", element: <Placeholder section="Settings" plan="#14c" /> },
        ],
      },
      { path: "lost-sessions", element: <Placeholder section="Lost Sessions" plan="#14b" /> },
      { path: "help", element: <Help /> },
      { path: "metrics", element: <Placeholder section="Metrics" plan="#14d" /> },
      { path: "settings/global", element: <Placeholder section="Global Settings" plan="#14c" /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
