"use client";

import { useState } from "react";
import { Send, Sparkles, FileText, Bot, User } from "lucide-react";
import Button from "../ui/Button";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: {
    id: string;
    type: string;
    description: string;
  }[];
  timestamp: Date;
  isError?: boolean;
}

interface AIAgentChatProps {
  claimId: string;
  isExpanded?: boolean;
}

// Suggested questions based on common review scenarios
const SUGGESTED_QUESTIONS = [
  "Was the conservative treatment requirement satisfied?",
  "Why is this claim recommended for approval/denial?",
  "What evidence supports the diagnosis?",
  "Are there any medication interaction concerns?",
  "Show me the patient's treatment timeline.",
  "Which policy requirement is uncertain?",
];

export default function AIAgentChat({ claimId, isExpanded = false }: AIAgentChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  // Only meaningful for the Agent Builder backend, which keeps
  // conversation state server-side -- passing it back lets a follow-up
  // question ("what severity is that?") resolve without resending full
  // claim context. The Bedrock backend ignores it and uses `history`
  // instead; harmless to send either way.
  const [conversationId, setConversationId] = useState<string | null>(null);

  const handleSend = async (question?: string) => {
    const messageText = question || input.trim();
    if (!messageText || loading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content: messageText,
      timestamp: new Date(),
    };

    // Prior turns as {role, content} only -- used by the Bedrock backend,
    // which re-sends full claim/adjudication context on every call.
    const history = messages.map((m) => ({ role: m.role, content: m.content }));

    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE_URL}/claims/${claimId}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: messageText, history, conversation_id: conversationId }),
      });
      if (!res.ok) {
        throw new Error(`Request failed (${res.status})`);
      }
      const data = await res.json();
      if (data.conversation_id) {
        setConversationId(data.conversation_id);
      }
      const aiResponse: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: data.answer,
        citations: data.citations,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, aiResponse]);
    } catch {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: "I couldn't reach the claim assistant just now. Please try again.",
          timestamp: new Date(),
          isError: true,
        },
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className={`card flex flex-col ${isExpanded ? "h-[600px]" : "h-[500px]"}`}>
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-slate-200 px-5 py-4">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-purple-100">
          <Sparkles size={16} className="text-purple-600" />
        </div>
        <div>
          <h3 className="text-sm font-semibold text-slate-900">AI Claim Assistant</h3>
          <p className="text-xs text-slate-500">Ask questions about {claimId}</p>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
        {messages.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-center">
            <Bot size={48} className="text-slate-300 mb-3" />
            <h4 className="text-sm font-semibold text-slate-700 mb-1">Start a Conversation</h4>
            <p className="text-sm text-slate-500 mb-4 max-w-sm">
              Ask questions about this claim's evidence, policy requirements, or treatment timeline.
            </p>

            {/* Suggested Questions */}
            <div className="w-full max-w-md space-y-2">
              <p className="text-xs font-medium text-slate-600 mb-2">Suggested questions:</p>
              {SUGGESTED_QUESTIONS.slice(0, 3).map((question, idx) => (
                <button
                  key={idx}
                  onClick={() => handleSend(question)}
                  className="w-full text-left text-xs text-slate-600 p-2 rounded-lg border border-slate-200 hover:border-blue-300 hover:bg-blue-50 transition-colors"
                >
                  {question}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <>
            {messages.map((message) => (
              <div
                key={message.id}
                className={`flex gap-3 ${message.role === "user" ? "justify-end" : ""}`}
              >
                {message.role === "assistant" && (
                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-purple-100">
                    <Bot size={16} className="text-purple-600" />
                  </div>
                )}

                <div className={`flex flex-col ${message.role === "user" ? "items-end" : ""} max-w-[80%]`}>
                  <div
                    className={`rounded-lg px-4 py-2.5 ${
                      message.role === "user"
                        ? "bg-blue-600 text-white"
                        : message.isError
                        ? "bg-red-50 text-red-700 border border-red-200"
                        : "bg-slate-100 text-slate-800"
                    }`}
                  >
                    <p className="text-sm whitespace-pre-wrap">{message.content}</p>
                  </div>

                  {/* Citations */}
                  {message.citations && message.citations.length > 0 && (
                    <div className="mt-2 space-y-1">
                      <p className="text-xs font-medium text-slate-600">Evidence:</p>
                      {message.citations.map((citation) => (
                        <button
                          key={citation.id}
                          className="flex items-center gap-2 text-xs text-blue-600 hover:underline"
                        >
                          <FileText size={12} />
                          {citation.description}
                        </button>
                      ))}
                    </div>
                  )}

                  <span className="mt-1 text-xs text-slate-400">
                    {message.timestamp.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                  </span>
                </div>

                {message.role === "user" && (
                  <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-blue-100">
                    <User size={16} className="text-blue-600" />
                  </div>
                )}
              </div>
            ))}

            {loading && (
              <div className="flex gap-3">
                <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-purple-100">
                  <Bot size={16} className="text-purple-600" />
                </div>
                <div className="bg-slate-100 rounded-lg px-4 py-2.5">
                  <div className="flex items-center gap-2">
                    <div className="flex gap-1">
                      <div className="h-2 w-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: "0ms" }} />
                      <div className="h-2 w-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: "150ms" }} />
                      <div className="h-2 w-2 rounded-full bg-slate-400 animate-bounce" style={{ animationDelay: "300ms" }} />
                    </div>
                    <span className="text-xs text-slate-500">AI is thinking...</span>
                  </div>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-slate-200 p-4">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyPress={handleKeyPress}
            placeholder="Ask about this claim..."
            disabled={loading}
            className="flex-1 rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-800 placeholder:text-slate-400 focus:border-blue-400 focus:outline-none focus:ring-2 focus:ring-blue-100 disabled:opacity-50"
          />
          <Button
            onClick={() => handleSend()}
            disabled={!input.trim() || loading}
            icon={<Send size={16} />}
            variant="primary"
          >
            Send
          </Button>
        </div>
      </div>
    </div>
  );
}

