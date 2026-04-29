import { Outlet } from "react-router";
import { TopBar } from "./TopBar";
import { Sidebar } from "./Sidebar";

export function Layout() {
  return (
    <div className="grid h-screen grid-rows-[auto_1fr] overflow-hidden">
      <TopBar />
      <div className="grid grid-cols-[16rem_1fr] overflow-hidden">
        <Sidebar />
        <main className="overflow-y-auto p-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
