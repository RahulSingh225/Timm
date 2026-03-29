'use client';

import { useState } from 'react';
import { Send, Bot, User, Database } from 'lucide-react';

interface ChatMessage {
    role: 'user' | 'model';
    content: string;
}

export default function TradingCoPilot() {
    const [messages, setMessages] = useState<ChatMessage[]>([]);
    const [input, setInput] = useState('');
    const [isLoading, setIsLoading] = useState(false);

    const sendMessage = async (e: React.FormEvent) => {
        e.preventDefault();
        if (!input.trim()) return;

        const userMsg: ChatMessage = { role: 'user', content: input };
        setMessages((prev) => [...prev, userMsg]);
        setInput('');
        setIsLoading(true);

        try {
            const res = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: userMsg.content,
                    history: messages // Pass history to maintain conversation state
                }),
            });

            const data = await res.json();

            if (data.reply) {
                setMessages((prev) => [...prev, { role: 'model', content: data.reply }]);
            }
        } catch (error) {
            console.error('Chat error:', error);
            setMessages((prev) => [...prev, { role: 'model', content: "Error: Unable to reach the RAG backend." }]);
        } finally {
            setIsLoading(false);
        }
    };

    return (
        <div className="flex flex-col h-[calc(100vh-4rem)] max-w-4xl mx-auto p-4 font-mono">
            {/* Header */}
            <div className="flex items-center gap-3 mb-6 pb-4 border-b border-neutral-800">
                <Database className="text-purple-500" size={24} />
                <div>
                    <h1 className="text-xl font-bold text-white">RAG Co-Pilot</h1>
                    <p className="text-xs text-neutral-500">Connected to PostgreSQL Vault & Local LLM (Ollama)</p>
                </div>
            </div>

            {/* Chat Window */}
            <div className="flex-1 overflow-y-auto space-y-6 mb-6 pr-2">
                {messages.length === 0 && (
                    <div className="text-center text-neutral-500 mt-20">
                        Ask me about setups, FII positioning, or specific options contracts.
                    </div>
                )}

                {messages.map((msg, idx) => (
                    <div key={idx} className={`flex gap-4 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                        {msg.role === 'model' && (
                            <div className="w-8 h-8 rounded bg-purple-500/20 flex items-center justify-center shrink-0 border border-purple-500/50">
                                <Bot size={18} className="text-purple-400" />
                            </div>
                        )}

                        <div className={`p-4 rounded-lg max-w-[80%] whitespace-pre-wrap ${msg.role === 'user'
                                ? 'bg-neutral-800 text-white'
                                : 'bg-neutral-900 border border-neutral-800 text-neutral-300'
                            }`}>
                            {msg.content}
                        </div>

                        {msg.role === 'user' && (
                            <div className="w-8 h-8 rounded bg-blue-500/20 flex items-center justify-center shrink-0 border border-blue-500/50">
                                <User size={18} className="text-blue-400" />
                            </div>
                        )}
                    </div>
                ))}
                {isLoading && (
                    <div className="flex gap-4">
                        <div className="w-8 h-8 rounded bg-purple-500/20 flex items-center justify-center shrink-0 border border-purple-500/50">
                            <span className="animate-ping h-2 w-2 bg-purple-400 rounded-full"></span>
                        </div>
                        <div className="p-4 text-neutral-500">Analyzing database context...</div>
                    </div>
                )}
            </div>

            {/* Input Box */}
            <form onSubmit={sendMessage} className="flex gap-3">
                <input
                    type="text"
                    value={input}
                    onChange={(e) => setInput(e.target.value)}
                    placeholder="e.g., Is Nifty 22000 CE a good scalp based on today's FII data?"
                    className="flex-1 bg-neutral-900 border border-neutral-800 rounded-lg px-4 py-3 text-white focus:outline-none focus:border-purple-500 transition-colors"
                    disabled={isLoading}
                />
                <button
                    type="submit"
                    disabled={isLoading || !input.trim()}
                    className="bg-purple-600 hover:bg-purple-500 text-white px-6 py-3 rounded-lg font-bold transition-colors disabled:opacity-50 flex items-center gap-2"
                >
                    Send <Send size={18} />
                </button>
            </form>
        </div>
    );
}