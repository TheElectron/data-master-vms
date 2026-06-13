import axios, { AxiosError } from "axios";
import type { ChatResponse } from "../types";

const client = axios.create({
  baseURL: "/api",
  headers: { "Content-Type": "application/json" },
  timeout: 120_000, // LLM responses can be slow
});

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function handleAxiosError(error: unknown): never {
  if (error instanceof AxiosError) {
    const msg = (error.response?.data as { error?: string })?.error ?? error.message;
    throw new ApiError(msg, error.response?.status);
  }
  throw error instanceof Error ? error : new Error(String(error));
}

export const chatApi = {
  sendMessage: async (question: string): Promise<ChatResponse> => {
    const { data } = await client
      .post<ChatResponse>("/chat", { question })
      .catch(handleAxiosError);
    return data;
  },
};
