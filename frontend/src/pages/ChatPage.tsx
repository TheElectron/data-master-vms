import { useCallback, useState } from "react";
import ChatWindow from "../components/chat/ChatWindow";
import InputBar from "../components/chat/InputBar";
import { chatApi } from "../services/api";
import type { Message } from "../types";

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  const handleSend = useCallback(async (question: string) => {
    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: "user",
      content: question,
    };
    const loadingId = crypto.randomUUID();
    const loadingMsg: Message = {
      id: loadingId,
      role: "assistant",
      content: "",
      isLoading: true,
    };

    setMessages((prev) => [...prev, userMsg, loadingMsg]);
    setIsLoading(true);

    try {
      const { answer, sources } = await chatApi.sendMessage(question);
      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadingId
            ? { ...m, content: answer, sources, isLoading: false }
            : m,
        ),
      );
    } catch {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === loadingId
            ? { ...m, content: "Something went wrong. Please try again.", isLoading: false }
            : m,
        ),
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  return (
    <div className="page">
      <header className="page-header">
        <h1>Tech News RAG</h1>
        <p>Answers grounded in this week's technology news</p>
      </header>
      <ChatWindow messages={messages} />
      <InputBar onSend={handleSend} disabled={isLoading} />
    </div>
  );
}
