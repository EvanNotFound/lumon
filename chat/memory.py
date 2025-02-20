import json
import os
from typing import List, Literal, Optional
from datetime import datetime

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
from utils.date import get_montreal_time

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


@tool
def save_recall_memory(memory: str, config: RunnableConfig) -> str:
    """Save memory to vectorstore for later semantic retrieval."""
    time_context = get_montreal_time()
    
    # Include the full formatted date in the memory content
    memory_with_date = f"On {time_context['formatted']}: {memory}"
    
    memory_id = str(uuid.uuid4())

    document = Document(
        page_content=memory_with_date,
        id=memory_id,
        metadata={
            "id": memory_id,
            "timestamp": time_context['datetime'].isoformat(),
            "day_of_week": time_context['day_of_week'],
            "date": time_context['date'],
            "time": time_context['time'],
            "timezone": time_context['timezone'],
            "is_edited": False,
            "original_timestamp": time_context['datetime'].isoformat(),  # Same as timestamp for new memories
            "edit_timestamp": None  # No edits yet
        }
    )
    recall_vector_store.add_documents([document])
    recall_vector_store.save_local(PERSIST_DIRECTORY)
    return memory_with_date

@tool
def search_recall_memories(query: str, config: RunnableConfig) -> List[str]:
    """Search for relevant memories."""
    documents = recall_vector_store.similarity_search(query, k=10)
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
            # Search for memories that contain the provided text
            docs = recall_vector_store.similarity_search(memory_text, k=5)
            matching_doc = None
            
            # Find exact match by checking if the memory text is contained in the full content
            for doc in docs:
                content = doc.page_content
                # Strip out the date prefix if it exists
                if ": " in content:
                    content = content.split(": ", 1)[1]
                # Strip out edit marker and everything after if it exists
                if " (Originally from " in content:
                    content = content.split(" (Originally from ")[0]
                
                if content.strip() == memory_text.strip():
                    matching_doc = doc
                    break
            
            if not matching_doc:
                results.append(f"Could not find exact memory: {memory_text}")
                continue
            
            doc_id = matching_doc.metadata.get('id')
            if not doc_id:
                results.append(f"Failed to delete (no ID): {memory_text}")
                continue

            recall_vector_store.delete([doc_id])
            deleted_count += 1
            results.append(f"Successfully deleted: {matching_doc.page_content}")
        
        # Only save if we actually deleted something
        if deleted_count > 0:
            recall_vector_store.save_local(PERSIST_DIRECTORY)
            
        return "\n".join(results)
        
    except Exception as e:
        error_msg = f"Error during memory deletion: {str(e)}"
        results.append(error_msg)
        return "\n".join(results)

@tool
def update_recall_memory(old_memory_text: str, new_memory_text: str, config: RunnableConfig) -> str:
    """Update an existing memory while preserving its original timestamp.
    
    Args:
        old_memory_text: The exact text of the memory to update
        new_memory_text: The new text to replace the old memory
    Returns:
        String describing the result of the update
    """
    try:
        # Find the existing memory
        docs = recall_vector_store.similarity_search(old_memory_text, k=5)
        matching_doc = None
        
        # Find exact match by checking if the memory text is contained in the full content
        for doc in docs:
            content = doc.page_content
            # Strip out the date prefix if it exists
            if ": " in content:
                content = content.split(": ", 1)[1]
            # Strip out edit marker and everything after if it exists
            if " (Originally from " in content:
                content = content.split(" (Originally from ")[0]
            
            if content.strip() == old_memory_text.strip():
                matching_doc = doc
                break
                
        if not matching_doc:
            return f"Could not find exact memory to update: {old_memory_text}"
        
        old_doc = matching_doc
        # Get the original timestamp and convert it from ISO format to datetime
        original_timestamp = old_doc.metadata.get('original_timestamp') or old_doc.metadata.get('timestamp')
        if original_timestamp:
            original_timestamp = datetime.fromisoformat(original_timestamp)
        
        doc_id = old_doc.metadata.get('id')
        
        if not doc_id:
            return "Failed to update: Could not find document ID"

        # Delete the old memory
        recall_vector_store.delete([doc_id])
        
        # Create new memory with original timestamp plus current edit time
        current_time = get_montreal_time()
        formatted_original_timestamp = get_montreal_time(original_timestamp).get('formatted')
        edited_memory = f"{new_memory_text} (Originally from {formatted_original_timestamp}, Edited on {current_time['formatted']})"

        new_memory_id = str(uuid.uuid4())
        
        # Create new document with updated content but preserve original metadata
        new_doc = Document(
            page_content=edited_memory,
            id=new_memory_id,
            metadata={
                "id": new_memory_id,
                "original_timestamp": original_timestamp,
                "edit_timestamp": current_time['datetime'].isoformat(),
                "day_of_week": current_time['day_of_week'],
                "date": current_time['date'],
                "time": current_time['time'],
                "timezone": current_time['timezone'],
                "is_edited": True
            }
        )
        
        # Add the updated memory and save
        recall_vector_store.add_documents([new_doc])
        recall_vector_store.save_local(PERSIST_DIRECTORY)
        
        return f"Successfully updated memory: {edited_memory}"
        
    except Exception as e:
        return f"Error updating memory: {str(e)}"

class State(MessagesState):
    # add memories that will be retrieved based on the conversation context
    recall_memories: List[str]

