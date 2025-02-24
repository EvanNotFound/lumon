from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
import os
from datetime import datetime
import uuid
from typing import Union, List, Dict

class MemoryTools:
    # Make these class variables instead of instance variables
    persist_directory = "data/memory_lumon"
    vector_store = None
    
    @classmethod
    def _initialize_store(cls) -> FAISS:
        """Helper method to initialize or load the vector store. Not for LLMs."""
        os.makedirs(cls.persist_directory, exist_ok=True)
        embeddings = OpenAIEmbeddings()
        try:
            return FAISS.load_local(
                cls.persist_directory,
                embeddings,
                allow_dangerous_deserialization=True
            )
        except Exception as e:
            print(f"Creating new vector store: {e}")
            initial_doc = Document(page_content="Memory store initialized.")
            store = FAISS.from_documents([initial_doc], embeddings)
            store.save_local(cls.persist_directory)
            return store

    @classmethod
    def __init__(cls):
        """Initialize the memory tools with FAISS vector store."""
        if cls.vector_store is None:
            cls.vector_store = cls._initialize_store()

    @classmethod
    def save_memory(cls, memory: str) -> Union[str, Dict]:
        """
        Save a memory to the vector store.

        Args:
            memory (str): The memory text to save.

        Returns:
            Union[str, Dict]: Success message with memory ID if saved, or error message if failed.
        """
        try:
            if not isinstance(memory, str) or not memory.strip():
                return "Error: Memory must be a non-empty string."

            memory_id = str(uuid.uuid4())
            timestamp = datetime.now().isoformat()
            
            document = Document(
                page_content=memory,
                metadata={
                    "id": memory_id,
                    "timestamp": timestamp
                }
            )
            
            cls.vector_store.add_documents([document])
            cls.vector_store.save_local(cls.persist_directory)
            
            print(f"Memory saved successfully: {memory_id}")
            return {
                "status": "success",
                "memory_id": memory_id,
                "message": f"Memory saved successfully"
            }
            
        except Exception as e:
            print(f"Error saving memory: {str(e)}")
            return f"Error saving memory: {str(e)}"

    @classmethod
    def search_memories(cls, query: str, limit: int = 5) -> Union[List[Dict], str]:
        """
        Search for relevant memories using semantic similarity.

        Args:
            query (str): The search query text.
            limit (int, optional): Maximum number of memories to return. Defaults to 5.

        Returns:
            Union[List[Dict], str]: List of matching memories with metadata, or error message if failed.
        """
        try:
            if not isinstance(query, str) or not query.strip():
                return "Error: Query must be a non-empty string."
            
            if not isinstance(limit, int) or limit < 1:
                return "Error: Limit must be a positive integer."

            documents = cls.vector_store.similarity_search(query, k=limit)
            
            results = []
            for doc in documents:
                results.append({
                    "content": doc.page_content,
                    "id": doc.metadata.get("id"),
                    "timestamp": doc.metadata.get("timestamp")
                })
            
            print(f"Found {len(results)} memories")
            return results

        except Exception as e:
            print(f"Error searching memories: {str(e)}")
            return f"Error searching memories: {str(e)}"
