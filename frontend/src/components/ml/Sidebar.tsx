"use client"
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { LayoutDashboard, BrainCircuit, Network, Route, Cpu, MessageSquare } from 'lucide-react';
import clsx from 'clsx';

const navItems = [
  { name: 'Overview', href: '/ml/overview', icon: LayoutDashboard },
  { name: 'Live Signals', href: '/ml/signals', icon: Route },
  { name: 'Evolved Strategies', href: '/ml/strategies', icon: BrainCircuit },
  { name: 'Neural & MARL', href: '/ml/evolution', icon: Cpu },
  { name: 'Sector GNN Map', href: '/ml/sectors', icon: Network },
  { name: 'Chat Advisor', href: '/ml/chat', icon: MessageSquare },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <div className="w-64 bg-neutral-900 border-r border-neutral-800 flex flex-col h-full shrink-0">
      <div className="h-16 flex items-center px-6 border-b border-neutral-800">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center font-bold text-white shadow shadow-indigo-500/20">
            T
          </div>
          <span className="font-semibold text-lg text-neutral-100 tracking-tight">Timm AI Desk</span>
        </div>
      </div>
      
      <div className="px-4 py-6 flex-1 overflow-y-auto">
        <div className="text-xs font-semibold text-neutral-500 uppercase tracking-wider mb-4 px-2">
          Intelligence Modules
        </div>
        <nav className="space-y-1">
          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.name}
                href={item.href}
                className={clsx(
                  "flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                  isActive 
                    ? "bg-indigo-500/10 text-indigo-400" 
                    : "text-neutral-400 hover:bg-neutral-800/50 hover:text-neutral-200"
                )}
              >
                <Icon size={18} className={isActive ? "text-indigo-400" : "text-neutral-500"} />
                {item.name}
              </Link>
            );
          })}
        </nav>
      </div>
      
      <div className="p-4 border-t border-neutral-800">
        <div className="bg-neutral-950 p-3 rounded-lg border border-neutral-800/50 shadow-inner">
          <p className="text-xs text-neutral-500">EC2 Worker Status</p>
          <div className="flex items-center gap-2 mt-1.5">
            <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)] animate-pulse"></div>
            <p className="text-sm font-medium text-emerald-400">Online • T4 GPU Active</p>
          </div>
        </div>
      </div>
    </div>
  );
}
