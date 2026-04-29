import { createBrowserRouter, RouterProvider } from "react-router";
import { Layout } from "./components/layout/Layout";
import { Overview } from "./pages/Overview";
import { ProjectView } from "./pages/ProjectView";
import { Help } from "./pages/Help";
import { Placeholder } from "./pages/Placeholder";

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
          { path: "sessions", element: <Placeholder section="Sessions" plan="#14b" /> },
          { path: "activity", element: <Placeholder section="Activity Center" plan="#14b" /> },
          { path: "suggestions", element: <Placeholder section="Suggestions" plan="#14b" /> },
          { path: "trash", element: <Placeholder section="Trash" plan="#14b" /> },
          { path: "snapshots", element: <Placeholder section="Snapshots" plan="#14b" /> },
          { path: "health", element: <Placeholder section="Health" plan="#14b" /> },
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
