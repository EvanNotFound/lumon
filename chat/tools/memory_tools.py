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
            current_time = datetime.now()
            timestamp = current_time.isoformat()
            
            # Enhanced metadata similar to memory.py
            document = Document(
                page_content=memory,
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
            
            return {
                "status": "success",
                "memory_id": memory_id,
                "message": "Memory saved successfully"
            }
            
        except Exception as e:
            print(f"Error saving memory: {str(e)}")
            return f"Error saving memory: {str(e)}"

    @classmethod
    def delete_memory(cls, memory_text: Union[str, List[str]]) -> str:
        """
        Delete one or more memories based on their exact text content.

        Args:
            memory_text: Single memory text or list of memory texts to delete

        Returns:
            str: Description of deletion results
        """
        if isinstance(memory_text, str):
            memory_text = [memory_text]
        
        results = []
        deleted_count = 0
        
        try:
            for text in memory_text:
                docs = cls.vector_store.similarity_search(text, k=5)
                matching_doc = None
                
                # Find exact match
                for doc in docs:
                    if doc.page_content.strip() == text.strip():
                        matching_doc = doc
                        break
                
                if not matching_doc:
                    results.append(f"Could not find exact memory: {text}")
                    continue
                
                doc_id = matching_doc.metadata.get('id')
                if not doc_id:
                    results.append(f"Failed to delete (no ID): {text}")
                    continue

                cls.vector_store.delete([doc_id])
                deleted_count += 1
                results.append(f"Successfully deleted: {matching_doc.page_content}")
            
            if deleted_count > 0:
                cls.vector_store.save_local(cls.persist_directory)
            
            print(f"DEBUG: Deleted {deleted_count} memories and {results}")
            return "\n".join(results)
            
        except Exception as e:
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
        try:
            docs = cls.vector_store.similarity_search(old_memory_text, k=5)
            matching_doc = None
            
            # Find exact match
            for doc in docs:
                if doc.page_content.strip() == old_memory_text.strip():
                    matching_doc = doc
                    break
                    
            if not matching_doc:
                return f"Could not find exact memory to update: {old_memory_text}"
            
            doc_id = matching_doc.metadata.get('id')
            if not doc_id:
                return "Failed to update: Could not find document ID"

            # Get original timestamp
            original_timestamp = matching_doc.metadata.get('original_timestamp') or matching_doc.metadata.get('timestamp')

            # Delete old memory
            cls.vector_store.delete([doc_id])
            
            # Create new memory with edit information
            current_time = datetime.now()
            edited_memory = f"{new_memory_text} (Edited on {current_time.isoformat()})"
            new_memory_id = str(uuid.uuid4())
            
            new_doc = Document(
                page_content=edited_memory,
                metadata={
                    "id": new_memory_id,
                    "timestamp": current_time.isoformat(),
                    "original_timestamp": original_timestamp,
                    "edit_timestamp": current_time.isoformat(),
                    "is_edited": True
                }
            )
            
            cls.vector_store.add_documents([new_doc])
            cls.vector_store.save_local(cls.persist_directory)
            
            return f"Successfully updated memory: {edited_memory}"
            
        except Exception as e:
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
            if (len(results) == 0):
                return "No memories found, memory list is empty"
            
            return results

        except Exception as e:
            print(f"Error searching memories: {str(e)}")
            return f"Error searching memories: {str(e)}"
