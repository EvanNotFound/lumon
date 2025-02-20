import json
import os
from typing import List, Literal, Optional

import tiktoken
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.messages import get_buffer_string
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from langchain_core.vectorstores import InMemoryVectorStore
from langchain_openai import ChatOpenAI
from langchain_openai.embeddings import OpenAIEmbeddings
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.prebuilt import ToolNode
from langchain.storage import LocalFileStore
from langchain_community.vectorstores import FAISS
from langchain_openai import OpenAIEmbeddings

PERSIST_DIRECTORY = "data/memory_store"

store = LocalFileStore(PERSIST_DIRECTORY)
embeddings = OpenAIEmbeddings()

os.makedirs(PERSIST_DIRECTORY, exist_ok=True)

# Initialize an empty vector store only if it doesn't exist
try:
    recall_vector_store = FAISS.load_local(
        PERSIST_DIRECTORY,
        embeddings,
        allow_dangerous_deserialization=True
    )
except Exception as e:
    print(f"No vector store found, creating a new one......")
    # Initialize empty vector store if none exists
    initial_memory = "You are a helpful assistant that can answer questions and help with tasks."
    initial_document = Document(page_content=initial_memory)

    recall_vector_store = FAISS.from_documents(
        documents=[initial_document],
        embedding=embeddings
    )
    recall_vector_store.save_local(PERSIST_DIRECTORY)
    print(f"New vector store created at {PERSIST_DIRECTORY}")

import uuid


def get_user_id(config: RunnableConfig) -> str:
    user_id = config["configurable"].get("user_id")
    if user_id is None:
        raise ValueError("User ID needs to be provided to save a memory.")

    return user_id


@tool
def save_recall_memory(memory: str, config: RunnableConfig) -> str:
    """Save memory to vectorstore for later semantic retrieval."""
    document = Document(
        page_content=memory,
        id=str(uuid.uuid4())
    )
    recall_vector_store.add_documents([document])
    recall_vector_store.save_local(PERSIST_DIRECTORY)
    return memory

@tool
def search_recall_memories(query: str, config: RunnableConfig) -> List[str]:
    """Search for relevant memories."""
    documents = recall_vector_store.similarity_search(query, k=5)
    return [document.page_content for document in documents]

@tool
def delete_recall_memory(query: str, config: RunnableConfig) -> str:
    """Delete a memory from the vector store."""
    # Find relevant memories
    similar_docs = recall_vector_store.similarity_search(query, k=1)
    if not similar_docs:
        return "No matching memory found to delete."
    
    # Get the document ID of the most similar memory
    doc_id = similar_docs[0].metadata.get('id') or similar_docs[0].id
    
    if not doc_id:
        return "Could not find document ID for deletion."

    try:
        recall_vector_store.delete([doc_id])
        recall_vector_store.save_local(PERSIST_DIRECTORY)
        return f"Memory deleted successfully: {similar_docs[0].page_content}"
    except Exception as e:
        return f"Error deleting memory: {str(e)}"

class State(MessagesState):
    # add memories that will be retrieved based on the conversation context
    recall_memories: List[str]

