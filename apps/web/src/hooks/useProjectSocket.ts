"use client";

import { useEffect, useRef, useCallback } from "react";
import { useAuthStore } from "@/stores/authStore";

export interface AgentMessage {
  type: "agent_message";
  content: string;
  /** True when this message asks the engineer to make a decision (auto-opens chat). */
  requires_input?: boolean;
  /** True when this is a complete, discrete message rather than a streamed chunk. */
  final?: boolean;
  /** Optional questionnaire form payload */
  questionnaire?: any;
}
export interface ChatHistoryMessage {
  type: "chat_history";
  messages: Array<{
    role: "user" | "assistant";
    content: string;
    timestamp?: string;
    questionnaire?: any;
  }>;
}
export interface StatusLog { type: "status_log"; tool: string; status: string }
export interface GateReached { type: "gate_reached"; gate: string; action_required: string }
export interface DrawingCommands { type: "drawing_commands"; data: unknown }
export interface DrawingUpdate { type: "drawing_update"; data: unknown }
export interface JobUpdate {
  type: "job_update";
  job_id: string;
  job_type: string;
  status: "queued" | "running" | "complete" | "failed" | "cancelled";
  progress_pct: number;
  current_step: string;
  result_url?: string | null;
  errors?: string[];
}
export interface SocketError { type: "error"; message: string }

export type SocketMessage =
  | AgentMessage
  | ChatHistoryMessage
  | StatusLog
  | GateReached
  | DrawingCommands
  | DrawingUpdate
  | JobUpdate
  | SocketError;

export interface SocketCallbacks {
  onAgentMessage?: (msg: AgentMessage) => void;
  onChatHistory?: (msg: ChatHistoryMessage) => void;
  onStatusLog?: (msg: StatusLog) => void;
  onGateReached?: (msg: GateReached) => void;
  onDrawingCommands?: (msg: DrawingCommands) => void;
  onJobUpdate?: (msg: JobUpdate) => void;
  onError?: (msg: SocketError) => void;
}

const WS_BASE =
  typeof window !== "undefined"
    ? (process.env.NEXT_PUBLIC_WS_URL ?? `ws://${window.location.hostname}:5000`)
    : "ws://localhost:5000";

export function useProjectSocket(
  projectId: string | null,
  callbacks: SocketCallbacks
) {
  const wsRef = useRef<WebSocket | null>(null);
  const callbacksRef = useRef(callbacks);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectDelayRef = useRef(1000);
  const unmountedRef = useRef(false);
  const connectRef = useRef<() => void>(() => {});

  const connect = useCallback(() => {
    if (!projectId || unmountedRef.current) return;

    const token = useAuthStore.getState().token;
    const url = `${WS_BASE}/ws/${projectId}${token ? `?token=${token}` : ""}`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectDelayRef.current = 1000;
    };

    ws.onmessage = (event) => {
      try {
        const msg: SocketMessage = JSON.parse(event.data as string);
        switch (msg.type) {
          case "agent_message":
            callbacksRef.current.onAgentMessage?.(msg);
            break;
          case "chat_history":
            callbacksRef.current.onChatHistory?.(msg as ChatHistoryMessage);
            break;
          case "status_log":
            callbacksRef.current.onStatusLog?.(msg);
            break;
          case "gate_reached":
            callbacksRef.current.onGateReached?.(msg);
            break;
          case "drawing_commands":
          case "drawing_update":
            callbacksRef.current.onDrawingCommands?.(msg as DrawingCommands);
            break;
          case "job_update":
            callbacksRef.current.onJobUpdate?.(msg as JobUpdate);
            break;
          case "error":
            callbacksRef.current.onError?.(msg);
            break;
        }
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      wsRef.current = null;
      if (!unmountedRef.current) {
        // Exponential backoff: 1 s → 2 s → 4 s … capped at 30 s
        reconnectTimerRef.current = setTimeout(() => {
          reconnectDelayRef.current = Math.min(
            reconnectDelayRef.current * 2,
            30_000
          );
          connectRef.current();
        }, reconnectDelayRef.current);
      }
    };

    ws.onerror = () => {
      ws.close();
    };
  }, [projectId]);

  const sendMessage = useCallback((content: string): boolean => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ content }));
      return true;
    }
    return false;
  }, []);

  useEffect(() => {
    callbacksRef.current = callbacks;
    connectRef.current = connect;
  }, [callbacks, connect]);

  useEffect(() => {
    unmountedRef.current = false;
    connect();
    return () => {
      unmountedRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { sendMessage };
}
