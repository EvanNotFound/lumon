from typing import List, Union, Dict
import os
import uuid
from datetime import datetime
from typing_extensions import TypedDict
from langchain_core.documents import Document
from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from utils.date import get_montreal_time
from utils.logger import logger

class TaskData(TypedDict):
    title: str
    completed: bool
    do_date: str
    due_date: str
    description: str
    category: str
    subject: str
    recurring: bool
    recurrence_pattern: dict

class TaskTools:
    # Class variables
    persist_directory = "data/task_lumon"
    vector_store = None

    @classmethod
    def _initialize_store(cls) -> FAISS:
        """Helper method to initialize or load the vector store.
        
        Returns:
            FAISS: Initialized FAISS vector store instance
        """
        logger.debug("Starting vector store initialization")
        os.makedirs(cls.persist_directory, exist_ok=True)
        embeddings = OpenAIEmbeddings()
        try:
            logger.debug(f"Attempting to load existing vector store from {cls.persist_directory}")
            store = FAISS.load_local(
                cls.persist_directory,
                embeddings,
                allow_dangerous_deserialization=True
            )
            logger.info("Successfully loaded existing task vector store")
            return store
        except Exception as e:
            logger.warn(f"Failed to load existing store, creating new one. Error: {e}")
            initial_doc = Document(page_content="Task store initialized.")
            store = FAISS.from_documents([initial_doc], embeddings)
            store.save_local(cls.persist_directory)
            logger.info("Successfully created new task vector store")
            return store

    @classmethod
    def __init__(cls):
        """Initialize the task tools with FAISS vector store."""
        print("Initializing TaskTools...")
        if cls.vector_store is None:
            cls.vector_store = cls._initialize_store()
        print("TaskTools initialization complete")

    @classmethod
    def save_task(cls, tasks: List[TaskData]) -> Union[str, Dict]:
        """Save tasks to the vector store.

        Args:
            tasks (List[TaskData]): List of task details in a structured format.
                Example:
                [
                    {
                        "title": "Finish report",
                        "completed": False,
                        "do_date": "2024-04-20",
                        "due_date": "2024-04-30",
                        "description": "Complete the quarterly report",
                        "category": "work",
                        "subject": "Math",
                        "recurring": True,
                        "recurrence_pattern": {
                            "type": "weekly",
                            "days": ["tuesday", "thursday"],
                            "end_date": "2024-12-31"
                        }
                    }
                ]

        Returns:
            Union[str, Dict]: On success, returns a dictionary containing:
                {
                    "status": "success",
                    "tasks": List[str],  # List of stored task titles
                    "message": str  # Success message
                }
                On failure, returns error message string.
        """
        logger.debug(f"Starting save_task operation for {len(tasks)} tasks")
        try:
            time_context = get_montreal_time()
            stored_tasks = []
            
            for task in tasks:
                logger.debug(f"Processing task: {task.get('title', 'NO TITLE')}")
                # Set default values for missing fields
                task_with_defaults = {
                    **task,
                    "subject": task.get("subject", ""),
                    "recurring": task.get("recurring", False),
                    "recurrence_pattern": task.get("recurrence_pattern", {})
                }

                recurrence_info = ""
                if task_with_defaults['recurring'] and task_with_defaults.get('recurrence_pattern'):
                    pattern = task_with_defaults['recurrence_pattern']
                    if pattern['type'] == 'weekly':
                        recurrence_info = f"Recurs weekly on: {', '.join(pattern['days'])}\n"
                        if 'end_date' in pattern:
                            recurrence_info += f"Until: {pattern['end_date']}\n"

                task_string = (
                    f"Title: {task_with_defaults['title']}\n"
                    f"Do: {task_with_defaults['do_date']}\n"
                    f"Due: {task_with_defaults['due_date']}\n"
                    f"Completed: {task_with_defaults['completed']}\n"
                    f"Description: {task_with_defaults['description']}\n"
                    f"Category: {task_with_defaults['category']}\n"
                    f"Subject: {task_with_defaults['subject']}\n"
                    f"Recurring: {task_with_defaults['recurring']}\n"
                    f"{recurrence_info}"
                    f"Stored on: {time_context['formatted']}"
                )

                task_id = str(uuid.uuid4())
                document = Document(
                    page_content=task_string,
                    id=task_id,
                    metadata={
                        "id": task_id,
                        "timestamp": time_context['datetime'].isoformat(),
                        **task_with_defaults
                    }
                )
                
                cls.vector_store.add_documents([document])
                stored_tasks.append(task["title"])
            
            cls.vector_store.save_local(cls.persist_directory)
            logger.info(f"Successfully stored {len(stored_tasks)} tasks")
            return {
                "status": "success",
                "tasks": stored_tasks,
                "message": f"Tasks stored successfully: {', '.join(stored_tasks)}"
            }
            
        except Exception as e:
            logger.error(f"Error saving tasks: {str(e)}")
            return f"Error saving tasks: {str(e)}"

    @classmethod
    def search_tasks(cls, query: str, limit: int = 5) -> Union[List[Dict], str]:
        """Search for tasks using semantic similarity.

        Args:
            query (str): The search query text
            limit (int, optional): Maximum number of tasks to return. Defaults to 5.

        Returns:
            Union[List[Dict], str]: On success, returns list of matching tasks:
                [
                    {
                        "content": str,  # Full task content
                        "metadata": dict  # Task metadata including id, timestamp, etc.
                    }
                ]
                On failure or no results, returns error message string.
        """
        logger.debug(f"Starting search_tasks with query: '{query}', limit: {limit}")
        try:
            if not isinstance(query, str) or not query.strip():
                logger.warn("Invalid query provided")
                return "Error: Query must be a non-empty string."

            logger.debug("Executing similarity search")
            documents = cls.vector_store.similarity_search(query, k=limit)
            
            results = []
            for doc in documents:
                logger.debug(f"Found matching task: {doc.metadata.get('title', 'NO TITLE')}")
                results.append({
                    "content": doc.page_content,
                    "metadata": doc.metadata
                })
            
            logger.info(f"Task search completed. Found {len(results)} tasks.")
            return results if results else "No tasks found"

        except Exception as e:
            logger.error(f"Error searching tasks: {str(e)}")
            return f"Error searching tasks: {str(e)}"

    @classmethod
    def delete_task(cls, id: str) -> str:
        """Delete a task based on its title or description.

        Args:
            id (str): The ID of the task to delete

        Returns:
            str: Message describing the result of the deletion operation:
                - Success message with count of deleted tasks
                - "No tasks were deleted" if no matching tasks found
                - Error message if operation fails
        """
        logger.debug(f"Starting delete_task operation for id: {id}")
        try:
            cls.vector_store.delete([id])
            cls.vector_store.save_local(cls.persist_directory)
            logger.info(f"Successfully deleted task with id: {id}") 
            return f"Successfully deleted task with id: {id}"
            
        except Exception as e:
            logger.error(f"Error deleting task: {str(e)}")
            return f"Error deleting task: {str(e)}"

    @classmethod
    def update_task(cls, old_task_text: str, updated_task: TaskData) -> str:
        """Update an existing task while preserving its metadata.

        Args:
            old_task_text (str): Text to match against task title or description
            updated_task (TaskData): New task data to replace the old task.
                Must follow the TaskData structure with all required fields.

        Returns:
            str: Message describing the result of the update operation:
                - Success message with updated task details
                - Error message if task not found or operation fails
        """
        print(f"Attempting to update task matching: {old_task_text}")
        try:
            # Find the existing task
            docs = cls.vector_store.similarity_search(old_task_text, k=5)
            matching_doc = None
            
            for doc in docs:
                metadata = doc.metadata
                if (old_task_text.lower() in metadata.get('title', '').lower() or 
                    old_task_text.lower() in metadata.get('description', '').lower()):
                    matching_doc = doc
                    break
                    
            if not matching_doc:
                return f"Could not find task matching: {old_task_text}"
            
            # Delete old task
            doc_id = matching_doc.metadata.get('id')
            if not doc_id:
                return "Failed to update: Could not find document ID"
            
            cls.vector_store.delete([doc_id])
            
            # Create updated task
            time_context = get_montreal_time()
            recurrence_info = ""
            if updated_task['recurring'] and updated_task.get('recurrence_pattern'):
                pattern = updated_task['recurrence_pattern']
                if pattern['type'] == 'weekly':
                    recurrence_info = f"Recurs weekly on: {', '.join(pattern['days'])}\n"
                    if 'end_date' in pattern:
                        recurrence_info += f"Until: {pattern['end_date']}\n"

            task_string = (
                f"Title: {updated_task['title']}\n"
                f"Do: {updated_task['do_date']}\n"
                f"Due: {updated_task['due_date']}\n"
                f"Completed: {updated_task['completed']}\n"
                f"Description: {updated_task['description']}\n"
                f"Category: {updated_task['category']}\n"
                f"Subject: {updated_task['subject']}\n"
                f"Recurring: {updated_task['recurring']}\n"
                f"{recurrence_info}"
                f"Updated on: {time_context['formatted']}"
            )

            new_task_id = str(uuid.uuid4())
            new_doc = Document(
                page_content=task_string,
                id=new_task_id,
                metadata={
                    "id": new_task_id,
                    "timestamp": time_context['datetime'].isoformat(),
                    **updated_task
                }
            )
            
            cls.vector_store.add_documents([new_doc])
            cls.vector_store.save_local(cls.persist_directory)
            
            return f"Successfully updated task:\n{task_string}"
            
        except Exception as e:
            print(f"Error updating task: {str(e)}")
            return f"Error updating task: {str(e)}"
