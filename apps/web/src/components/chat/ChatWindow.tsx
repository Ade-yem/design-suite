"use client";

import { useState } from "react";
import MessageList from "./MessageList";
import InputArea from "./InputArea";
import Sidebar from "./Sidebar";
import Header from "./Header";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  imageUrl?: string;
}

export default function ChatWindow() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isSidebarOpen, setIsSidebarOpen] = useState(true);
  const [projectTitle, setProjectTitle] = useState("New Project");
  const [confirmedMembers, setConfirmedMembers] = useState<any[]>([]);

  const handleSendMessage = async (
    content: string,
    file: File | null,
    action = "parse",
    data: any = null
  ) => {
    // Set project title on first message if it's "New Project"
    if (projectTitle === "New Project" && content) {
      setProjectTitle(
        content.slice(0, 20) + (content.length > 20 ? "..." : "")
      );
    }

    const newMessage: Message = {
      id: Date.now().toString(),
      role: "user",
      content,
      imageUrl: file ? URL.createObjectURL(file) : undefined,
    };

    setMessages((prev) => [...prev, newMessage]);
    setIsLoading(true);

    try {
      const formData = new FormData();
      formData.append("message", content);
      formData.append("action", action);

      if (file) {
        formData.append("file", file);
      }

      if (data) {
        formData.append("data", JSON.stringify(data));
      }

      const response = await fetch("/api/chat", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error("Failed to send message");
      }

      const responseData = await response.json();

      let assistantContent = "";
      if (responseData.type === "design_result") {
        assistantContent = JSON.stringify(responseData, null, 2);
      } else {
        // Assume it's parser output
        // Inject request_type for standard selection if members are present
        if (responseData.members) {
          responseData.request_type = "select_standard";
        }
        assistantContent = JSON.stringify(responseData, null, 2);
      }

      const assistantMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: assistantContent,
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      console.error("Error sending message:", error);
      const errorMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: "Sorry, I encountered an error processing your request.",
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleArtifactAction = (action: string, data: any) => {
    if (action === "confirm_members") {
      setConfirmedMembers(data);
      const confirmMsg: Message = {
        id: Date.now().toString(),
        role: "user",
        content: "I have reviewed and confirmed the structural members.",
      };
      setMessages((prev) => [...prev, confirmMsg]);
    } else if (action === "select_standard") {
      const payload = {
        extracted_params: { members: confirmedMembers },
        selected_standard: data,
      };
      handleSendMessage(
        `Selected Standard: ${data}. Proceeding with design...`,
        null,
        "design",
        payload
      );
    }
  };

  return (
    <div className="flex h-screen w-full bg-white dark:bg-black">
      {/* Sidebar */}
      <Sidebar
        isOpen={isSidebarOpen}
        onToggle={() => setIsSidebarOpen(!isSidebarOpen)}
      />

      {/* Main Content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <Header
          onToggleSidebar={() => setIsSidebarOpen(!isSidebarOpen)}
          projectTitle={projectTitle}
        />

        <div className="flex flex-1 flex-col overflow-hidden bg-white dark:bg-black">
          <div className="mx-auto flex h-full w-full max-w-[800px] flex-col">
            <MessageList
              messages={messages}
              isLoading={isLoading}
              onArtifactAction={handleArtifactAction}
            />
            <InputArea
              onSendMessage={(msg, file) => handleSendMessage(msg, file)}
              disabled={isLoading}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
