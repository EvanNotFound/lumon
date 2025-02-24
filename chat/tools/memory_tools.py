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
        print("Initializing vector store...")
        os.makedirs(cls.persist_directory, exist_ok=True)
        embeddings = OpenAIEmbeddings()
        try:
            store = FAISS.load_local(
                cls.persist_directory,
                embeddings,
                allow_dangerous_deserialization=True
            )
            print("Successfully loaded existing vector store")
            return store
        except Exception as e:
            print(f"Creating new vector store: {e}")
            initial_doc = Document(page_content="Memory store initialized.")
            store = FAISS.from_documents([initial_doc], embeddings)
            store.save_local(cls.persist_directory)
            print("Successfully created new vector store")
            return store

    @classmethod
    def __init__(cls):
        """Initialize the memory tools with FAISS vector store."""
        print("Initializing MemoryTools...")
        if cls.vector_store is None:
            cls.vector_store = cls._initialize_store()
        print("MemoryTools initialization complete")

    @classmethod
    def save_memory(cls, memory: str) -> Union[str, Dict]:
        """
        Save a memory to the vector store.

        Args:
            memory (str): The memory text to save.

        Returns:
            Union[str, Dict]: Success message with memory ID if saved, or error message if failed.
        """
        print(f"Attempting to save new memory...")
        try:
            if not isinstance(memory, str) or not memory.strip():
                print("Error: Empty or invalid memory content")
                return "Error: Memory must be a non-empty string."

            memory_id = str(uuid.uuid4())
            current_time = datetime.now()
            timestamp = current_time.isoformat()
            
            # Enhanced metadata similar to memory.py
            document = Document(
                page_content=memory,
                id=memory_id,
                metadata={
                    "id": memory_id,
                    "timestamp": timestamp,
                    "original_timestamp": timestamp,  # Same as timestamp for new memories
                    "edit_timestamp": None,  # No edits yet
                    "is_edited": False
                }
            )
            
            cls.vector_store.add_documents([document])
            cls.vector_store.save_local(cls.persist_directory)
            
            print(f"Successfully saved memory with ID: {memory_id}")
            return {
                "status": "success",
                "memory_id": memory_id,
                "message": "Memory saved successfully"
            }
            
        except Exception as e:
            print(f"Error saving memory: {str(e)}")
            return f"Error saving memory: {str(e)}"

    @classmethod
    def delete_memory(cls, id: str) -> str:
        """
        Delete a memory based on its ID.

        Args:
            id: The ID of the memory to delete

        Returns:
            str: Description of deletion results
        """
        try:
            print(f"Attempting to delete memory with ID: {id}")
            cls.vector_store.delete([id])
            cls.vector_store.save_local(cls.persist_directory)
            print(f"Successfully deleted memory with ID: {id}")
            return f"Successfully deleted memory {id}"
        except Exception as e:
            print(f"Error deleting memory with ID {id}: {str(e)}")
            return f"Error during memory deletion: {str(e)}"

    @classmethod
    def update_memory(cls, old_memory_text: str, new_memory_text: str) -> str:
        """
        Update an existing memory while preserving its original timestamp.

        Args:
            old_memory_text: The exact text of the memory to update
            new_memory_text: The new text to replace the old memory

        Returns:
            str: Description of update results
        """
        print(f"Attempting to update memory...")
        try:
            print("Searching for memory to update...")
            docs = cls.vector_store.similarity_search(old_memory_text, k=5)
            matching_doc = None
            
            # Find exact match
            for doc in docs:
                if doc.page_content.strip() == old_memory_text.strip():
                    matching_doc = doc
                    break
                    
            if not matching_doc:
                print(f"Could not find exact memory to update")
                return f"Could not find exact memory to update: {old_memory_text}"
            
            doc_id = matching_doc.metadata.get('id')
            if not doc_id:
                print("Failed to find document ID")
                return "Failed to update: Could not find document ID"

            print(f"Found memory to update with ID: {doc_id}")
            original_timestamp = matching_doc.metadata.get('original_timestamp') or matching_doc.metadata.get('timestamp')

            # Delete old memory
            print("Deleting old memory version...")
            cls.vector_store.delete([doc_id])
            
            # Create new memory with edit information
            current_time = datetime.now()
            edited_memory = f"{new_memory_text} (Edited on {current_time.isoformat()})"
            new_memory_id = str(uuid.uuid4())
            
            new_doc = Document(
                page_content=edited_memory,
                id=new_memory_id,
                metadata={
                    "id": new_memory_id,
                    "timestamp": current_time.isoformat(),
                    "original_timestamp": original_timestamp,
                    "edit_timestamp": current_time.isoformat(),
                    "is_edited": True
                }
            )
            
            print("Saving updated memory...")
            cls.vector_store.add_documents([new_doc])
            cls.vector_store.save_local(cls.persist_directory)
            
            print(f"Successfully updated memory with new ID: {new_memory_id}")
            return f"Successfully updated memory: {edited_memory}"
            
        except Exception as e:
            print(f"Error updating memory: {str(e)}")
            return f"Error updating memory: {str(e)}"

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
        print(f"Searching memories with query: '{query}' (limit: {limit})")
        try:
            if not isinstance(query, str):
                print("Error: Invalid query type")
                return "Error: Query must be a string."
            if not query.strip():
                print("Error: Empty query")
                return "Error: Empty query is not allowed. Please provide a search term."
            
            if not isinstance(limit, int) or limit < 1:
                print("Error: Invalid limit value")
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
            if (len(results) == 0):
                print("No memories found")
                return "No memories found, memory list is empty"
            
            return results

        except Exception as e:
            print(f"Error searching memories: {str(e)}")
            return f"Error searching memories: {str(e)}"
