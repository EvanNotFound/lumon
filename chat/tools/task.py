from typing import List
import os
import uuid
from typing_extensions import TypedDict
from langchain_core.documents import Document
from langchain_core.tools import tool
from langchain_community.vectorstores import FAISS
from langchain_openai.embeddings import OpenAIEmbeddings
from utils.date import get_montreal_time
from langchain_core.runnables import RunnableConfig

PERSIST_TASK_DIRECTORY = "data/task_store"
os.makedirs(PERSIST_TASK_DIRECTORY, exist_ok=True)
embeddings = OpenAIEmbeddings()

# Try to load an existing vector store for tasks;
# if not found, create a new one.
try:
    task_vector_store = FAISS.load_local(
        PERSIST_TASK_DIRECTORY,
        embeddings,
        allow_dangerous_deserialization=True
    )
except Exception as e:
    print("No task vector store found, creating a new one...")
    initial_task = "Task vector store initialized."
    initial_document = Document(page_content=initial_task)
    task_vector_store = FAISS.from_documents([initial_document], embeddings)
    task_vector_store.save_local(PERSIST_TASK_DIRECTORY)
    print(f"New task vector store created at {PERSIST_TASK_DIRECTORY}")

class TaskData(TypedDict):
    title: str
    completed: bool
    do_date: str
    due_date: str  # ISO format string
    description: str
    category: str
    subject: str
    recurring: bool
    recurrence_pattern: dict

@tool
def save_task(tasks: List[TaskData], config: RunnableConfig) -> str:
    """
    Save a list of tasks to the structured task vector store.
    
    Args:
        tasks (List[TaskData]): A list of task details in a structured format.
            Example:
            [
                {
                    "title": "Finish report",
                    "completed": False,
                    "do_date": "2024-04-20 Sunday", 
                    "due_date": "2024-04-30 Wednesday", 
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
        str: Confirmation message listing the stored task titles.
    """
    time_context = get_montreal_time()
    stored_titles = []
    for task in tasks:
        recurrence_info = ""
        if task['recurring'] and task.get('recurrence_pattern'):
            pattern_str = task['recurrence_pattern']
            # Parse the pattern string into components
            if "weekly on" in pattern_str:
                days = pattern_str.split("weekly on ")[1].split(" until ")[0]
                end_date = pattern_str.split(" until ")[1] if " until " in pattern_str else None
                recurrence_info = f"Recurs weekly on: {days}\n"
                if end_date:
                    recurrence_info += f"Until: {end_date}\n"

        task_string = (
            f"Title: {task['title']}\n"
            f"Do: {task['do_date']}\n"
            f"Due: {task['due_date']}\n"
            f"Completed: {task['completed']}\n"
            f"Description: {task['description']}\n"
            f"Category: {task['category']}\n"
            f"Subject: {task['subject']}\n"
            f"Recurring: {task['recurring']}\n"
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
                **task
            }
        )
        task_vector_store.add_documents([document])
        stored_titles.append(task["title"])
    task_vector_store.save_local(PERSIST_TASK_DIRECTORY)
    return f"Tasks stored successfully: {', '.join(stored_titles)}"

@tool
def search_task(query: str, config: RunnableConfig, k: int = 5) -> List[str]:
    """
    Search for tasks relevant to a given query.
    
    Args:
        query (str): The search query.
        k (int): Number of top matching tasks to return (default is 5).
    
    Returns:
        List[str]: List of matching task strings.
    """
    documents = task_vector_store.similarity_search(query, k=k)
    return [doc.page_content for doc in documents]

@tool
def delete_task(task_texts: str | list[str], config: RunnableConfig) -> str:
    """Delete one or more tasks based on their title or description.
    
    Args:
        task_texts: Single task text or list of task texts to delete
    Returns:
        String describing the results of deletion attempts
    """
    if isinstance(task_texts, str):
        task_texts = [task_texts]
    
    results = []
    deleted_count = 0
    
    try:
        for task_text in task_texts:
            # Search for tasks that contain the provided text
            docs = task_vector_store.similarity_search(task_text, k=5)
            matching_docs = []
            
            # Find matches based on title or description
            for doc in docs:
                metadata = doc.metadata
                if (task_text.lower() in metadata.get('title', '').lower() or 
                    task_text.lower() in metadata.get('description', '').lower()):
                    matching_docs.append(doc)
            
            if not matching_docs:
                results.append(f"Could not find task matching: {task_text}")
                continue
            
            # Delete all matching tasks
            for matching_doc in matching_docs:
                doc_id = matching_doc.metadata.get('id')
                if not doc_id:
                    results.append(f"Failed to delete (no ID): {matching_doc.page_content}")
                    continue

                task_vector_store.delete([doc_id])
                deleted_count += 1
                results.append(f"Successfully deleted: {matching_doc.metadata.get('title', 'Untitled Task')}")
        
        # Only save if we actually deleted something
        if deleted_count > 0:
            task_vector_store.save_local(PERSIST_TASK_DIRECTORY)
            
        return "\n".join(results)
        
    except Exception as e:
        error_msg = f"Error during task deletion: {str(e)}"
        results.append(error_msg)
        return "\n".join(results)

@tool
def update_task(old_task_text: str, config: RunnableConfig, updated_task: TaskData) -> str:
    """Update an existing task while preserving its original metadata.
    
    Args:
        old_task_text: Text to match against task title or description
        updated_task: The new task data to replace the old task
    Returns:
        String describing the result of the update
    """
    try:
        # Find the existing task
        docs = task_vector_store.similarity_search(old_task_text, k=5)
        matching_doc = None
        
        # Find best match based on title or description
        for doc in docs:
            metadata = doc.metadata
            if (old_task_text.lower() in metadata.get('title', '').lower() or 
                old_task_text.lower() in metadata.get('description', '').lower()):
                matching_doc = doc
                break
                
        if not matching_doc:
            return f"Could not find task matching: {old_task_text}"
        
        doc_id = matching_doc.metadata.get('id')
        if not doc_id:
            return "Failed to update: Could not find document ID"

        # Delete the old task
        task_vector_store.delete([doc_id])
        
        # Create new task
        time_context = get_montreal_time()
        
        # Format recurrence information
        recurrence_info = ""
        if updated_task['recurring'] and 'recurrence_pattern' in updated_task:
            pattern = updated_task['recurrence_pattern']
            if pattern['type'] == 'weekly':
                recurrence_info = f"Recurs weekly on: {', '.join(pattern['days'])}\n"
            elif pattern['type'] == 'monthly':
                recurrence_info = f"Recurs monthly on day: {pattern['day_of_month']}\n"
            if 'end_date' in pattern:
                recurrence_info += f"Until: {pattern['end_date']}\n"

        # Create the task string
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
        
        # Create new document
        new_doc = Document(
            page_content=task_string,
            id=new_task_id,
            metadata={
                "id": new_task_id,
                "timestamp": time_context['datetime'].isoformat(),
                **updated_task
            }
        )
        
        # Add the updated task and save
        task_vector_store.add_documents([new_doc])
        task_vector_store.save_local(PERSIST_TASK_DIRECTORY)
        
        return f"Successfully updated task:\n{task_string}"
        
    except Exception as e:
        return f"Error updating task: {str(e)}" 