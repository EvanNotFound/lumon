from mainframe_orchestra import Task, Agent, OpenaiModels, Conduct, set_verbosity
from chat.agents.web_research import web_research_agent
from chat.agents.memory_management import memory_management_agent
from chat.agents.task_management import task_management_agent
from utils.date import get_montreal_time
from chat.tools.task_tools import TaskTools
from chat.tools.memory_tools import MemoryTools
from typing import Dict
import yaml
import tiktoken
from utils.logger import logger

def load_prompt_sections() -> Dict[str, str]:
    """Load prompt sections from YAML configuration"""
    with open('config/prompts.yaml', 'r') as file:
        return yaml.safe_load(file)

lumon_agent = Agent(
    agent_id="lumon_agent",
    role="Conductor",
    goal="To chat with and help the human user by coordinating your team of agents to carry out tasks.",
    attributes="""You know that you must use the conduct_tool to delegate tasks to your team of agents. 
    The conduct_tool accepts an array of tasks, where each task has:
    - task_id: a unique identifier for the task
    - agent_id: the agent to execute the task (web_research_agent, memory_management_agent, or task_management_agent)
    - instruction: what you want the agent to do
    
    Example usage:
    {"tasks": [{"task_id": "search_tasks", "agent_id": "task_management_agent", "instruction": "Search for all tasks"}]}
    """,
    llm=OpenaiModels.gpt_4o_mini,  # Or your preferred model
    temperature=0.7,
    tools=[
        Conduct.conduct_tool(web_research_agent, memory_management_agent, task_management_agent)
    ]
)

def create_lumon_task(user_input: str, conversation_history: list):
    time_context = get_montreal_time()

    # Construct context with loaded sections
    context = f"""
Current time in Montreal: {time_context["formatted"]}
"""
    
    # Initialize tiktoken encoder
    enc = tiktoken.encoding_for_model("gpt-4o-mini")

    # Convert conversation history to strings if they're dictionaries
    conversation_str = "\n".join(
        msg["content"] if isinstance(msg, dict) else str(msg) 
        for msg in conversation_history
    )

    # Calculate token count
    input_tokens = len(enc.encode(context + "\n\n" + conversation_str + "\n\n" + user_input))
    
    response = Task.create(
        agent=lumon_agent,
        context=context,
        messages=conversation_history,
        instruction=user_input,
        # stream=True,
        initial_response=True
    )

    response_tokens = len(enc.encode(response))
    total_tokens = input_tokens + response_tokens
    logger.debug(f"Token count: {total_tokens} total" \
                f" ({input_tokens} input, {response_tokens} response)")

    return response

def process_message(user_input: str, conversation_history: list):
    """Process a user message and return the response with token count"""
    
    # Get response
    response = create_lumon_task(user_input, conversation_history)

    
    # Add token count information
    # token_info = f"\n\n---\nTokens used: {total_tokens} total" \
    #              f" ({input_tokens} input, {response_tokens} response)"
    
    return response