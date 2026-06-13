"use client";

import { useState, useRef, useEffect } from "react";
import { Send, User, CheckCircle2, X } from "lucide-react";
import { useUIStore } from "@/stores/uiStore";
import { cn } from "@/lib/utils";
import { useProjectSocket } from "@/hooks/useProjectSocket";
import { GATE_LABELS } from "@/lib/pipelineStatus";
import { PRODUCT_NAME } from "@/lib/brand";
import { MarkdownRenderer } from "./MarkdownRenderer";
import { QuestionnaireForm, type Questionnaire } from "./QuestionnaireForm";
import { BlueprintIcon } from "./BlueprintIcon";
import { useAuthStore } from "@/stores/authStore";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: Date;
  questionnaire?: Questionnaire;
}

interface ChatSidebarProps {
  projectId: string;
  onGateReached?: (gate: string) => void;
  onClose?: () => void;
}

function TypingIndicator({ state }: { state: "" | "thinking" | "working" }) {
  return (
    <div className="flex items-start gap-3 animate-fade-in-up">
      <div className="h-7 w-7 rounded-md bg-primary/15 flex items-center justify-center shrink-0 mt-0.5">
        <BlueprintIcon className="h-5 w-5" state={state || "thinking"} />
      </div>
      <div className="flex items-center gap-1.5 py-3">
        <div className="h-2 w-2 rounded-full bg-primary typing-dot" />
        <div className="h-2 w-2 rounded-full bg-primary typing-dot" />
        <div className="h-2 w-2 rounded-full bg-primary typing-dot" />
      </div>
    </div>
  );
}

const WELCOME = (name?: string | null): Message => ({
  id: "welcome",
  role: "assistant",
  content:
    `Welcome ${name ? name : ""} to ${PRODUCT_NAME}.`,
  timestamp: new Date(),
});

export function ChatSidebar({ projectId, onGateReached, onClose }: ChatSidebarProps) {
  const { chatOpen, setChatOpen, incrementUnread, pendingGate, setPendingGate } =
    useUIStore();
  const {user} = useAuthStore();
  const message: Message = WELCOME(user?.full_name);
  const [messages, setMessages] = useState<Message[]>([message]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [agentState, setAgentState] = useState<"" | "thinking" | "working">("");
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Accumulate streaming chunks into a single assistant message
  const streamingIdRef = useRef<string | null>(null);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`;
  }, [input]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
      return;
    }

    if (e.key === "Enter" && e.shiftKey) {
      e.preventDefault();
      const textarea = textareaRef.current;
      if (!textarea) return;

      const start = textarea.selectionStart;
      const end = textarea.selectionEnd;
      const text = textarea.value;

      const lineStart = text.lastIndexOf("\n", start - 1) + 1;
      const currentLine = text.substring(lineStart, start);

      const unorderedMatch = currentLine.match(/^(\s*[-*])\s+(.*)/);
      const orderedMatch = currentLine.match(/^(\s*(\d+)\.)\s+(.*)/);

      let continuation = "\n";

      if (unorderedMatch) {
        const marker = unorderedMatch[1];
        const content = unorderedMatch[2];
        if (content.trim() === "") {
          const newLineText = text.substring(0, lineStart) + text.substring(start);
          setInput(newLineText);
          setTimeout(() => {
            textarea.selectionStart = textarea.selectionEnd = lineStart;
          }, 0);
          return;
        } else {
          continuation += marker + " ";
        }
      } else if (orderedMatch) {
        const num = parseInt(orderedMatch[2], 10);
        const content = orderedMatch[3];
        if (content.trim() === "") {
          const newLineText = text.substring(0, lineStart) + text.substring(start);
          setInput(newLineText);
          setTimeout(() => {
            textarea.selectionStart = textarea.selectionEnd = lineStart;
          }, 0);
          return;
        } else {
          continuation += `${num + 1}. `;
        }
      }

      const newText = text.substring(0, start) + continuation + text.substring(end);
      setInput(newText);

      setTimeout(() => {
        textarea.selectionStart = textarea.selectionEnd = start + continuation.length;
      }, 0);
    }
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
    onChatHistory: ({ messages }) => {
      setMessages([
        ...messages.map((m, idx) => ({
          id: `hist-${idx}-${Date.now()}`,
          role: m.role,
          content: m.content,
          timestamp: m.timestamp ? new Date(m.timestamp) : new Date(),
          questionnaire: m.questionnaire as Questionnaire | undefined,
        })),
      ]);
    },
    onAgentMessage: ({ content, requires_input, final, questionnaire }) => {
      // A decision-required message must surface the chat even when it is
      // collapsed — every chat-based engineer decision lives in this column.
      if (requires_input) setChatOpen(true);

      // `final` messages are complete, discrete node messages — render each as
      // its own bubble. Chunks (no `final`) accumulate into the streaming one.
      if (final || !streamingIdRef.current) {
        setIsTyping(false);
        setAgentState("");
        const id = `msg-${Date.now()}`;
        streamingIdRef.current = id;
        if (!chatOpen) incrementUnread();
        setMessages((prev) => [
          ...prev,
          { id, role: "assistant", content, timestamp: new Date(), questionnaire: questionnaire as Questionnaire | undefined },
        ]);
        if (final) streamingIdRef.current = null;
      } else {
        setAgentState("thinking");
        setIsTyping(true);
        appendChunk(content);
      }
    },
    onStatusLog: ({ tool, status }) => {
      const toolName = tool.replace(/_/, " ");
      if (status === "running") {
        setAgentState("working");
        setIsTyping(true);
        setMessages((prev) => [
          ...prev,
          {
            id: `log-run-${Date.now()}`,
            role: "assistant",
            content: `🔧 Analyst is running ${toolName}...`,
            timestamp: new Date(),
          },
        ]);
      } else {
        setAgentState("");
        setIsTyping(false);
        setMessages((prev) => [
          ...prev,
          {
            id: `log-end-${Date.now()}`,
            role: "assistant",
            content: `✓ ${toolName} complete`,
            timestamp: new Date(),
          },
        ]);
      }
    },
    onJobUpdate: ({ status }) => {
      if (status === "running") {
        setAgentState("working");
        setIsTyping(true);
      } else if (status === "complete" || status === "failed" || status === "cancelled") {
        setAgentState("");
        setIsTyping(false);
      }
    },
    onGateReached: ({ gate }) => {
      streamingIdRef.current = null;
      setAgentState("");
      setIsTyping(false);
      // A gate is a decision point — surface the chat even when collapsed.
      setChatOpen(true);
      // The gate identity is shared via the UI store so the always-visible
      // pipeline rail can host the approval; the chat only points to it.
      setPendingGate({ gate, label: GATE_LABELS[gate] ?? `Gate: ${gate}` });
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

    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
    }
  };

  return (
    <div className="h-full flex flex-col bg-card border-r border-border">
      {/* Header */}
      <div className="h-8 px-3 border-b border-border flex items-center gap-2 shrink-0">
        <BlueprintIcon className="h-4.5 w-4.5 shrink-0" state={agentState} />
        <span className="text-xs text-muted-foreground font-mono flex-1 truncate">
          {agentState === "working" ? "Analyst calculating..." : agentState === "thinking" ? "Analyst thinking..." : "Connected"}
        </span>
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
        {messages.map((msg, index) => {
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
            <div key={msg.id} className="space-y-3">
              <div
                className={cn(
                  "flex items-start gap-3 animate-fade-in-up",
                  msg.role === "user" && "flex-row-reverse"
                )}
              >
                <div
                  className={cn(
                    "h-7 w-7 rounded-md flex items-center justify-center shrink-0 mt-0.5",
                    msg.role === "assistant" ? "bg-primary/15" : "bg-secondary"
                  )}
                >
                  {msg.role === "assistant" ? (
                    <BlueprintIcon className="h-5 w-5" />
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
                  {msg.role === "user" ? (
                    msg.content
                  ) : (
                    <MarkdownRenderer content={msg.content} />
                  )}
                </div>
              </div>

              {/* Dynamic questionnaire form if it is the active/latest assistant message */}
              {msg.role === "assistant" &&
                msg.questionnaire?.fields &&
                index === messages.length - 1 && (
                  <div className="pl-10 pr-2 animate-fade-in-up">
                    <QuestionnaireForm
                      title={msg.questionnaire.title}
                      description={msg.questionnaire.description}
                      fields={msg.questionnaire.fields}
                      onSubmit={(formattedResponse) => {
                        // Append the formatted user message to state local log
                        const userMsgId = `msg-${Date.now()}`;
                        setMessages((prev) => [
                          ...prev,
                          {
                            id: userMsgId,
                            role: "user",
                            content: formattedResponse,
                            timestamp: new Date(),
                          },
                        ]);
                        setIsTyping(true);
                        sendMessage(formattedResponse);
                      }}
                    />
                  </div>
                )}
            </div>
          );
        })}
        {isTyping && <TypingIndicator state={agentState} />}

        {/* Gate pointer — the approval itself lives in the pipeline rail. */}
        {pendingGate && (
          <div className="rounded-lg border border-primary/40 bg-primary/5 px-3 py-3 space-y-2 animate-fade-in-up">
            <div className="flex items-center gap-2">
              <CheckCircle2 className="h-4 w-4 text-primary shrink-0" />
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
        <div className="flex items-start gap-2 bg-muted rounded-lg px-3 py-2">
          <textarea
            ref={textareaRef}
            rows={1}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about structural elements…"
            className="flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground resize-none py-1 max-h-[200px] overflow-y-auto scrollbar-thin"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim()}
            className={cn(
              "p-1.5 rounded-md transition-colors shrink-0 mt-0.5",
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
