import { useState, useRef, useEffect } from "react";
import { Send, Bot, User, Paperclip } from "lucide-react";
import { cn } from "@/lib/utils";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
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

const initialMessages: Message[] = [
  {
    id: "1",
    role: "assistant",
    content: "Welcome to StructAI Copilot. Upload a DXF file to begin structural analysis. I'll parse the geometry, identify members, and guide you through verification.",
    timestamp: new Date(),
  },
];

export function ChatSidebar() {
  const [messages, setMessages] = useState<Message[]>(initialMessages);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, isTyping]);

  const handleSend = () => {
    if (!input.trim()) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: input,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsTyping(true);

    setTimeout(() => {
      setIsTyping(false);
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: "I'm ready to help. Upload a DXF file using the canvas area or the attachment button to get started with structural analysis.",
          timestamp: new Date(),
        },
      ]);
    }, 1500);
  };

  return (
    <div className="h-full flex flex-col bg-card border-r border-border">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border flex items-center gap-2">
        <div className="h-2 w-2 rounded-full bg-success animate-pulse" />
        <span className="text-sm font-medium">StructAI Agent</span>
        <span className="text-xs text-muted-foreground ml-auto font-mono">v1.0</span>
      </div>

      {/* Messages */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-4 py-4 space-y-4 scrollbar-thin">
        {messages.map((msg) => (
          <div key={msg.id} className={cn("flex items-start gap-3 animate-fade-in-up", msg.role === "user" && "flex-row-reverse")}>
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
        ))}
        {isTyping && <TypingIndicator />}
      </div>

      {/* Input */}
      <div className="p-3 border-t border-border">
        <div className="flex items-center gap-2 bg-muted rounded-lg px-3 py-2">
          <button className="text-muted-foreground hover:text-foreground transition-colors">
            <Paperclip className="h-4 w-4" />
          </button>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSend()}
            placeholder="Ask about structural elements..."
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
