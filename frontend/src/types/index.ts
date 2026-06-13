export interface Source {
  title: string;
  url: string;
  published_at: string;
}

export interface Message {
  id: string;
  role: "user" | "assistant";
  content: string;
  sources?: Source[];
  isLoading?: boolean;
}

export interface ChatResponse {
  answer: string;
  sources: Source[];
}
