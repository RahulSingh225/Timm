'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Activity, MessageSquare, Target, LayoutDashboard, Radar, Briefcase } from 'lucide-react';

const navItems = [
    { href: '/', label: 'Command Center', icon: LayoutDashboard },
    { href: '/screener', label: 'Intraday Screener', icon: Radar },
    { href: '/trades', label: 'Active Trades', icon: Briefcase },
    { href: '/vectors', label: 'Vector Lab', icon: Target },
    { href: '/chat', label: 'AI Chat', icon: MessageSquare },
];

export function Navigation() {
    const pathname = usePathname();

    return (
        <nav className="border-b border-neutral-800 bg-neutral-950/80 backdrop-blur-xl sticky top-0 z-50">
            <div className="max-w-screen-2xl mx-auto px-6">
                <div className="flex items-center justify-between h-14">
                    {/* Brand */}
                    <Link href="/" className="flex items-center gap-2.5 group">
                        <div className="relative">
                            <Activity
                                size={22}
                                className="text-purple-500 group-hover:text-purple-400 transition-colors"
                            />
                            <div className="absolute -inset-1 bg-purple-500/20 rounded-full blur-sm opacity-0 group-hover:opacity-100 transition-opacity" />
                        </div>
                        <span className="text-lg font-bold tracking-tight text-white">
                            TIMM
                            <span className="text-neutral-500 text-[10px] ml-1.5 font-normal align-super">
                                QUANT
                            </span>
                        </span>
                    </Link>

                    {/* Nav Links */}
                    <div className="flex items-center gap-1">
                        {navItems.map((item) => {
                            const isActive = pathname === item.href;
                            const Icon = item.icon;
                            return (
                                <Link
                                    key={item.href}
                                    href={item.href}
                                    className={`
                                        flex items-center gap-2 px-3.5 py-2 rounded-lg text-sm font-medium transition-all duration-200
                                        ${isActive
                                            ? 'bg-neutral-800/80 text-white shadow-sm shadow-purple-500/5 border border-neutral-700/50'
                                            : 'text-neutral-400 hover:text-neutral-200 hover:bg-neutral-800/40 border border-transparent'
                                        }
                                    `}
                                >
                                    <Icon
                                        size={15}
                                        className={isActive ? 'text-purple-400' : 'text-neutral-500'}
                                    />
                                    {item.label}
                                </Link>
                            );
                        })}
                    </div>

                    {/* Status Indicator */}
                    <div className="flex items-center gap-2 text-xs text-neutral-500">
                        <div className="h-1.5 w-1.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.5)]" />
                        <span>Systems Online</span>
                    </div>
                </div>
            </div>
        </nav>
    );
}
