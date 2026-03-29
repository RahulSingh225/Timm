'use client';

import { useState, useRef, useEffect } from 'react';
import { Send, Cpu, User, Sparkles, Binary } from 'lucide-react';
import Link from 'next/link';

interface ChatMessage {
    role: 'user' | 'model';
    content: string;
}

export default function VanillaChat() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);
    const scrollRef = useRef<HTMLDivElement>(null);

    useEffect(() => {
        if (scrollRef.current) {
            scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
        }
    }, [messages]);

    const sendMessage = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim() || isLoading) return;

        const userMsg: ChatMessage = { role: 'user', content: input };
        setMessages((prev) => [...prev, userMsg]);
        setInput('');
        setIsLoading(true);

        try {
            const res = await fetch('/api/chat/vanilla', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: userMsg.content,
                    history: messages.slice(-10) // Only send last 10 messages for context
                }),
            });

            const data = await res.json();

            if (data.reply) {
                setMessages((prev) => [...prev, { role: 'model', content: data.reply }]);
            } else if (data.error) {
                setMessages((prev) => [...prev, { role: 'model', content: `Error: ${data.error}` }]);
            }
        } catch (error) {
            console.error('Chat error:', error);
            setMessages((prev) => [...prev, { role: 'model', content: "Error: Unable to reach the Vanilla LLM backend." }]);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex flex-col h-[calc(100vh-4rem)] max-w-5xl mx-auto p-6 font-sans bg-black/20 backdrop-blur-xl rounded-2xl border border-white/5 my-4">
            {/* Header */}
            <div className="flex items-center justify-between mb-8 pb-6 border-b border-white/10">
                <div className="flex items-center gap-4">
                    <div className="p-3 bg-blue-500/10 rounded-xl border border-blue-500/20">
                        <Cpu className="text-blue-400" size={28} />
                    </div>
                    <div>
                        <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-400 to-indigo-400 bg-clip-text text-transparent">Vanilla LLM</h1>
                        <p className="text-xs text-neutral-500 flex items-center gap-1.5">
                            <Sparkles size={12} className="text-blue-500" /> 
                            Direct Raw Interface (Ollama llama3.2)
                        </p>
                    </div>
                </div>
                <Link 
                    href="/chat" 
                    className="flex items-center gap-2 text-xs font-semibold px-4 py-2 bg-purple-500/10 hover:bg-purple-500/20 text-purple-400 rounded-lg border border-purple-500/20 transition-all"
                >
                    <Binary size={14} /> Switch to Analyst Mode (RAG)
                </Link>
            </div>

            {/* Chat Window */}
            <div ref={scrollRef} className="flex-1 overflow-y-auto space-y-6 mb-8 px-4 scrollbar-thin scrollbar-thumb-white/10 scrollbar-track-transparent">
                {messages.length === 0 && (
                    <div className="flex flex-col items-center justify-center h-full text-center space-y-6 opacity-40">
                        <div className="w-20 h-20 rounded-3xl bg-blue-500/5 flex items-center justify-center border border-blue-500/10 animate-pulse">
                            <Cpu size={40} className="text-blue-500" />
                        </div>
                        <div className="max-w-md">
                            <h3 className="text-lg font-medium text-white mb-2">Zero Context Interaction</h3>
                            <p className="text-sm text-neutral-400">
                                This mode communicates directly with the LLM without searching the market database. Use this for general coding, creative writing, or non-trading questions.
                            </p>
                        </div>
                    </div>
                )}

                {messages.map((msg, idx) => (
                    <div key={idx} className={`flex gap-5 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        {msg.role === 'model' && (
                            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-blue-600/20 to-indigo-600/20 flex items-center justify-center shrink-0 border border-blue-500/20 shadow-lg shadow-blue-500/5">
                                <Cpu size={20} className="text-blue-400" />
                            </div>
                        )}

                        <div className={`p-5 rounded-2xl max-w-[85%] whitespace-pre-wrap leading-relaxed transition-all shadow-sm ${msg.role === 'user'
                                ? 'bg-indigo-600 text-white shadow-indigo-500/10'
                                : 'bg-neutral-900/80 border border-white/5 text-neutral-200'
                            }`}>
                            {msg.content}
                        </div>

                        {msg.role === 'user' && (
                            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 flex items-center justify-center shrink-0 border border-indigo-500/20">
                                <User size={20} className="text-indigo-400" />
                            </div>
                        )}
                    </div>
                ))}
                
                {isLoading && (
                    <div className="flex gap-5">
                        <div className="w-10 h-10 rounded-xl bg-blue-500/10 flex items-center justify-center shrink-0 border border-blue-500/20">
                            <div className="flex gap-1">
                                <span className="w-1 h-1 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.3s]"></span>
                                <span className="w-1 h-1 bg-blue-400 rounded-full animate-bounce [animation-delay:-0.15s]"></span>
                                <span className="w-1 h-1 bg-blue-400 rounded-full animate-bounce"></span>
                            </div>
                        </div>
                        <div className="bg-neutral-900/40 p-5 rounded-2xl border border-white/5 text-neutral-500 text-sm animate-pulse italic">
                            Ollama is generating response...
                        </div>
                    </div>
                )}
            </div>

            {/* Input Box */}
            <form onSubmit={sendMessage} className="relative group">
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="Message Vanilla LLM..."
                    className="w-full bg-neutral-900/60 border border-white/10 rounded-2xl pl-6 pr-16 py-5 text-white placeholder:text-neutral-600 focus:outline-none focus:border-blue-500/50 focus:ring-4 focus:ring-blue-500/5 transition-all"
                    disabled={isLoading}
                />
                <button
                    type="submit"
                    disabled={isLoading || !input.trim()}
                    className="absolute right-3 top-1/2 -translate-y-1/2 bg-blue-600 hover:bg-blue-500 text-white p-3 rounded-xl transition-all disabled:opacity-30 disabled:grayscale flex items-center justify-center shadow-lg shadow-blue-600/20"
                >
                    <Send size={20} />
                </button>
            </form>
            
            <p className="text-[10px] text-neutral-600 mt-4 text-center uppercase tracking-widest font-bold">
                Direct Stream Protocol | No Market Context | LLAMA-3.2-8B
            </p>
        </div>
    );
}
