import MemberTable from "../artifacts/MemberTable";
import StandardSelector from "../artifacts/StandardSelector";

interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  imageUrl?: string;
}

interface MessageListProps {
  messages: Message[];
  isLoading?: boolean;
  onArtifactAction: (action: string, data: any) => void;
}

export default function MessageList({
  messages,
  isLoading,
  onArtifactAction,
}: MessageListProps) {
  const renderContent = (msg: Message) => {
    if (msg.role === "assistant") {
      try {
        // Try to parse as JSON to see if it's an artifact
        const data = JSON.parse(msg.content);
        
        // Check if it's a Member Table artifact (has 'members' array)
        if (data.members && Array.isArray(data.members)) {
          return (
            <div className="mt-2">
              <p className="mb-2 text-sm text-zinc-600 dark:text-zinc-300">
                I have extracted the following structural members. Please review and confirm:
              </p>
              <MemberTable
                initialMembers={data.members}
                onConfirm={(updatedMembers) =>
                  onArtifactAction("confirm_members", updatedMembers)
                }
              />
            </div>
          );
        }

        // Check if it's a Standard Selection request
        if (data.request_type === "select_standard") {
          return (
            <div className="mt-2">
              <p className="mb-2 text-sm text-zinc-600 dark:text-zinc-300">
                Please select the design standard to proceed:
              </p>
              <StandardSelector
                onSelect={(standard) =>
                  onArtifactAction("select_standard", standard)
                }
              />
            </div>
          );
        }
      } catch (e) {
        // Not JSON, render as text
      }
    }
    return <div className="whitespace-pre-wrap text-sm">{msg.content}</div>;
  };

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-6">
      {messages.map((msg) => (
        <div
          key={msg.id}
          className={`flex ${
            msg.role === "user" ? "justify-end" : "justify-start"
          }`}
        >
          <div
            className={`max-w-[90%] rounded-lg px-4 py-3 ${
              msg.role === "user"
                ? "bg-black text-white dark:bg-white dark:text-black"
                : "bg-zinc-100 text-zinc-900 dark:bg-zinc-900 dark:text-zinc-100"
            }`}
          >
            {msg.imageUrl && (
              <img
                src={msg.imageUrl}
                alt="Uploaded content"
                className="mb-3 max-h-64 rounded-md object-contain"
              />
            )}
            {renderContent(msg)}
          </div>
        </div>
      ))}
      {isLoading && (
        <div className="flex justify-start">
          <div className="rounded-lg bg-zinc-100 px-4 py-3 dark:bg-zinc-900">
            <div className="flex gap-1">
              <div className="h-2 w-2 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.3s]"></div>
              <div className="h-2 w-2 animate-bounce rounded-full bg-zinc-400 [animation-delay:-0.15s]"></div>
              <div className="h-2 w-2 animate-bounce rounded-full bg-zinc-400"></div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
