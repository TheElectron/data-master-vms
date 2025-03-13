import os
from langchain_ollama import OllamaEmbeddings, ChatOllama
from langchain_openai import AzureOpenAIEmbeddings, AzureChatOpenAI

class Models:
    def __init__(self):
        # ollama pull mxbai-embed-large
        self.embeddings_ollama = OllamaEmbeddings(
            model="mxbai-embed-large"
        )

        # ollama pull llama3.2
        self.model_ollama = ChatOllama(
            model="llama3.2",
            temperature=0,
        )