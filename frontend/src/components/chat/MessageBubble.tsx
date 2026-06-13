import type { Message } from "../../types";

interface Props {
  message: Message;
}

export default function MessageBubble({ message }: Props) {
  const isUser = message.role === "user";

  return (
    <div className={`message-row ${isUser ? "message-row--user" : "message-row--assistant"}`}>
      <div className={`bubble ${isUser ? "bubble--user" : "bubble--assistant"}`}>
        {message.isLoading ? (
          <span className="loading-dots" aria-label="Thinking…">
            <span />
            <span />
            <span />
          </span>
        ) : (
          <>
            <p className="bubble-content">{message.content}</p>

            {!isUser && message.sources && message.sources.length > 0 && (
              <div className="sources">
                <p className="sources-label">Sources</p>
                <ul className="sources-list">
                  {message.sources.map((src, i) => (
                    <li key={i}>
                      {src.url ? (
                        <a href={src.url} target="_blank" rel="noopener noreferrer">
                          {src.title || src.url}
                        </a>
                      ) : (
                        <span>{src.title}</span>
                      )}
                      {src.published_at && (
                        <span className="source-date">
                          {" · "}
                          {src.published_at.slice(0, 10)}
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
