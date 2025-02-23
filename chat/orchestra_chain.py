from mainframe_orchestra import Task, Agent, OpenaiModels
from langgraph.checkpoint.memory import MemorySaver
from utils.date import get_montreal_time
from chat.memory import save_recall_memory, search_recall_memories, delete_specific_memory, update_recall_memory
from chat.think import think_before_action, reflect_on_action
from chat.tools.date_tool import parse_date
from chat.tools.task import save_task, search_task, delete_task, update_task
from chat.tools.calculation import add, multiply

# Import and wrap LangChain tools
# tavily_search = LangchainTools.get_tool("TavilySearchResults")
# openai_embeddings = LangchainTools.get_tool("OpenAIEmbeddings")
# vector_store = LangchainTools.get_tool("FAISSVectorStore")

# Create custom tools wrapper for your existing tools
class CustomTools:
    @staticmethod
    def wrap_tool(tool_func):
        """Wrapper to make existing tools compatible with Orchestra"""
        def wrapped_tool(*args, **kwargs):
            try:
                return tool_func(*args, **kwargs)
            except Exception as e:
                return f"Error executing tool: {str(e)}"
        return wrapped_tool

# Wrap existing custom tools
tools = {
    # LangChain tools wrapped via LangchainTools
    # tavily_search,
    
    # Custom tools wrapped manually
    CustomTools.wrap_tool(add),
    CustomTools.wrap_tool(multiply),
    CustomTools.wrap_tool(save_recall_memory),
    CustomTools.wrap_tool(search_recall_memories),
    CustomTools.wrap_tool(delete_specific_memory),
    CustomTools.wrap_tool(update_recall_memory),
    CustomTools.wrap_tool(think_before_action),
    CustomTools.wrap_tool(reflect_on_action),
    CustomTools.wrap_tool(parse_date),
    CustomTools.wrap_tool(save_task),
    CustomTools.wrap_tool(search_task),
    CustomTools.wrap_tool(delete_task),
    CustomTools.wrap_tool(update_task)
}

# Define the main assistant agent
assistant = Agent(
    role="JARVIS",
    goal="serve as a helpful AI assistant with advanced memory capabilities",
    attributes="""
    - Efficient and concise in responses
    - Maintains long-term memory through external tools
    - Thinks carefully before taking actions
    - Handles tasks and scheduling with precision
    """,
    llm=OpenaiModels.gpt_4o_mini,  # Or your preferred model
    tools=tools
)

def create_assistant_task(user_input: str, memory_context: dict = None):
    # Format memory context
    recall_memories = memory_context.get('recall_memories', []) if memory_context else []
    time_context = get_montreal_time().get('formatted')
    
    memory_str = "<recall_memory>\n" + "\n".join(recall_memories) + "\n</recall_memory>"
    
    # Use the same system prompt structure
    context = f"""
Current time context: {time_context}

{memory_str}

IMPORTANT: Before discussing ANY task-related information, you MUST:
1. First use the search_task tool to find relevant tasks, with a high k value (e.g. 100)
2. Then process and summarize the results
3. Never rely on task_list from the context

When dealing with dates and time:
1. Always use the parse_date tool to validate and format dates
2. Never make up or assume dates without validation
3. For future dates, explicitly mention they are tentative or planned
4. When discussing schedules, deadlines, or appointments:
   - First validate the date with parse_date
   - Consider the current time context
   - Be explicit about time zones
   - Highlight if a date is in the past
   - ALWAYS use save_task to store any mentioned tasks, assignments, or deadlines

Memory Usage Guidelines:
1. Actively use memory tools (save_recall_memory, update_recall_memory)
2. Cross-reference new information with existing memories
3. Update outdated information using update_recall_memory
4. Store emotional context and personal values alongside facts

Thinking Process:
1. Use think_before_action for complex requests
2. Use reflect_on_action to evaluate responses
3. Think carefully before significant actions
"""

    return Task.create(
        agent=assistant,
        context=context,
        instruction=user_input
    )

# Memory management remains the same using LangGraph
memory_saver = MemorySaver()

def process_message(user_input: str, memory_context: dict = None):
    """Process a user message and return the response"""
    task = create_assistant_task(user_input, memory_context)
    response = task.execute()
    
    # Save to memory if needed
    if memory_context is not None:
        memory_saver.save({"messages": [response]})
    
    return response 