export default function MLLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-screen bg-black text-white selection:bg-indigo-500/30">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0 bg-neutral-950">
        <Topbar />
        <main className="flex-1 overflow-y-auto p-6 scroll-smooth">
          {children}
        </main>
      </div>
    </div>
  );
}

import Sidebar from "@/components/ml/Sidebar";
import Topbar from "@/components/ml/Topbar";
