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
def delete_specific_memory(memory_texts: str | list[str], config: RunnableConfig) -> str:
    """Delete one or more memories based on their exact text content.
    Args:
        memory_texts: Single memory text or list of memory texts to delete
    Returns:
        String describing the results of deletion attempts
    """
    if isinstance(memory_texts, str):
        memory_texts = [memory_texts]
    
    results = []
    deleted_count = 0
    
    try:
        for memory_text in memory_texts:
            docs = recall_vector_store.similarity_search(memory_text, k=1)
            if not docs or docs[0].page_content != memory_text:
                results.append(f"Could not find exact memory: {memory_text}")
                continue
            
            doc = docs[0]
            doc_id = doc.metadata.get('id') or doc.id
            if not doc_id:
                results.append(f"Failed to delete (no ID): {memory_text}")
                continue

            recall_vector_store.delete([doc_id])
            deleted_count += 1
            results.append(f"Successfully deleted: {memory_text}")
        
        # Only save if we actually deleted something
        if deleted_count > 0:
            recall_vector_store.save_local(PERSIST_DIRECTORY)
            
        return "\n".join(results)
        
    except Exception as e:
        error_msg = f"Error during memory deletion: {str(e)}"
        results.append(error_msg)
        return "\n".join(results)

class State(MessagesState):
    # add memories that will be retrieved based on the conversation context
    recall_memories: List[str]

