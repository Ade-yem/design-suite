"use client";

import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, CheckCircle2, X } from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { cn } from "@/lib/utils";
import { useProjectSocket } from "@/hooks/useProjectSocket";
import { GATE_LABELS } from "@/lib/pipelineStatus";
import { PRODUCT_NAME } from "@/lib/brand";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
}

interface ChatSidebarProps {
  projectId: string;
  onGateReached?: (gate: string) => void;
  onClose?: () => void;
}

function TypingIndicator() {
  return (
    <div className="flex items-start gap-3 animate-fade-in-up">
      <div className="h-7 w-7 rounded-md bg-primary/15 flex items-center justify-center flex-shrink-0 mt-0.5">
        <Bot className="h-4 w-4 text-primary" />
      </div>
      <div className="flex items-center gap-1.5 py-3">
        <div className="h-2 w-2 rounded-full bg-primary typing-dot" />
        <div className="h-2 w-2 rounded-full bg-primary typing-dot" />
        <div className="h-2 w-2 rounded-full bg-primary typing-dot" />
      </div>
    </div>
  );
}

const WELCOME: Message = {
  id: "welcome",
  role: "assistant",
  content:
    `Welcome to ${PRODUCT_NAME}. Upload a DXF or PDF file to begin structural analysis. I'll parse the geometry, identify members, and guide you through each stage.`,
  timestamp: new Date(),
};

export function ChatSidebar({ projectId, onGateReached, onClose }: ChatSidebarProps) {
  const { chatOpen, incrementUnread, pendingGate, setPendingGate } =
    useUIStore();
  const [messages, setMessages] = useState<Message[]>([WELCOME]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  // Accumulate streaming chunks into a single assistant message
  const streamingIdRef = useRef<string | null>(null);

  const appendAssistantAndNotify = (content: string) => {
    if (!chatOpen) incrementUnread();
    appendAssistant(content);
  };

  const appendAssistant = (content: string) => {
    const id = `msg-${Date.now()}`;
    streamingIdRef.current = id;
    setMessages((prev) => [
      ...prev,
      { id, role: "assistant", content, timestamp: new Date() },
    ]);
    setIsTyping(false);
  };

  const appendChunk = (chunk: string) => {
    const sid = streamingIdRef.current;
    if (!sid) {
      appendAssistant(chunk);
      return;
    }
    setMessages((prev) =>
      prev.map((m) => (m.id === sid ? { ...m, content: m.content + chunk } : m))
    );
  };

  const { sendMessage } = useProjectSocket(projectId, {
    onAgentMessage: ({ content }) => {
      if (!streamingIdRef.current) {
        setIsTyping(false);
        appendAssistantAndNotify(content);
      } else {
        appendChunk(content);
      }
    },
    onStatusLog: ({ tool }) => {
      setMessages((prev) => [
        ...prev,
        {
          id: `log-${Date.now()}`,
          role: "assistant",
          content: `✓ ${tool} complete`,
          timestamp: new Date(),
        },
      ]);
    },
    onGateReached: ({ gate }) => {
      streamingIdRef.current = null;
      // The gate identity is shared via the UI store so the always-visible
      // pipeline rail can host the approval; the chat only points to it.
      setPendingGate({ gate, label: GATE_LABELS[gate] ?? `Gate: ${gate}` });
      if (!chatOpen) incrementUnread();
      onGateReached?.(gate);
    },
    onError: ({ message }) => {
      setIsTyping(false);
      streamingIdRef.current = null;
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: `Error: ${message}`,
          timestamp: new Date(),
        },
      ]);
    },
  });

  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [messages, isTyping, pendingGate]);

  const handleSend = () => {
    if (!input.trim()) return;
    const text = input.trim();

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    streamingIdRef.current = null;

    const sent = sendMessage(text);
    if (sent) {
      setIsTyping(true);
    } else {
      setMessages((prev) => [
        ...prev,
        {
          id: `err-${Date.now()}`,
          role: "assistant",
          content: "Not connected to the pipeline. Please wait and try again.",
          timestamp: new Date(),
        },
      ]);
    }
  };

  return (
    <div className="h-full flex flex-col bg-card border-r border-border">
      {/* Header */}
      <div className="h-8 px-3 border-b border-border flex items-center gap-2 flex-shrink-0">
        <div className="h-1.5 w-1.5 rounded-full bg-success animate-pulse" />
        <span className="text-xs text-muted-foreground font-mono flex-1">Connected</span>
        {onClose && (
          <button
            onClick={onClose}
            className="p-1 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            aria-label="Hide chat"
          >
            <X className="h-3 w-3" />
          </button>
        )}
      </div>

      {/* Messages */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto px-4 py-4 space-y-4 scrollbar-thin"
      >
        {messages.map((msg) => {
          // Detect status events: messages that start with ✓ or 🔧
          const isStatusEvent =
            msg.role === "assistant" &&
            (msg.content.startsWith("✓") || msg.content.startsWith("🔧"));

          if (isStatusEvent) {
            return (
              <div
                key={msg.id}
                className="flex items-center justify-center py-2 animate-fade-in-up border-t border-b border-border/30"
              >
                <span className="text-xs text-foreground/40 font-mono">
                  {msg.content}
                </span>
              </div>
            );
          }

          return (
            <div
              key={msg.id}
              className={cn(
                "flex items-start gap-3 animate-fade-in-up",
                msg.role === "user" && "flex-row-reverse"
              )}
            >
              <div
                className={cn(
                  "h-7 w-7 rounded-md flex items-center justify-center flex-shrink-0 mt-0.5",
                  msg.role === "assistant" ? "bg-primary/15" : "bg-secondary"
                )}
              >
                {msg.role === "assistant" ? (
                  <Bot className="h-4 w-4 text-primary" />
                ) : (
                  <User className="h-4 w-4 text-muted-foreground" />
                )}
              </div>
              <div
                className={cn(
                  "rounded-lg px-3 py-2 text-sm leading-relaxed max-w-[85%]",
                  msg.role === "assistant"
                    ? "bg-muted text-foreground"
                    : "bg-primary text-primary-foreground"
                )}
              >
                {msg.content}
              </div>
            </div>
          );
        })}
        {isTyping && <TypingIndicator />}

        {/* Gate pointer — the approval itself lives in the pipeline rail. */}
        {pendingGate && (
          <div className="rounded-lg border border-primary/40 bg-primary/5 px-3 py-3 space-y-2 animate-fade-in-up">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-primary flex-shrink-0" />
              <p className="text-xs font-medium text-primary">Review Required</p>
            </div>
            <p className="text-xs text-muted-foreground">{pendingGate.label}</p>
            <p className="text-xs text-muted-foreground">
              Approve this step in the{" "}
              <span className="font-medium text-primary">pipeline rail</span> to
              continue.
            </p>
          </div>
        )}
      </div>

      {/* Input */}
      <div className="p-3 border-t border-border">
        <div className="flex items-center gap-2 bg-muted rounded-lg px-3 py-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Ask about structural elements…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className={cn(
              "p-1.5 rounded-md transition-colors",
              input.trim()
                ? "bg-primary text-primary-foreground hover:bg-primary/90"
                : "text-muted-foreground"
            )}
          >
            <Send className="h-3.5 w-3.5" />
          </button>
        </div>
      </div>
    </div>
  );
}
