"use client";

import { useState } from "react";
import { AppHeader } from "@/components/AppHeader";
import { ChatSidebar } from "@/components/ChatSidebar";
import { CanvasViewport } from "@/components/CanvasViewport";
import type { Stage } from "@/components/StageTracker";

const Index = () => {
  const [currentStage] = useState<Stage>("parsing");

  return (
    <div className="h-screen flex flex-col overflow-hidden">
      <AppHeader currentStage={currentStage} />
      <div className="flex-1 flex min-h-0">
        <div className="w-80 shrink-0">
          <ChatSidebar />
        </div>
        <div className="flex-1 min-w-0">
          <CanvasViewport />
        </div>
      </div>
    </div>
  );
};

export default Index;
