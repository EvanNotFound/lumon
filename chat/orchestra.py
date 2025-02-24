from mainframe_orchestra import Task, Agent, OpenaiModels, Conduct, set_verbosity
from chat.agents.web_research import web_research_agent
from chat.agents.memory_management import memory_management_agent
from chat.agents.task_management import task_management_agent
from utils.date import get_montreal_time
from chat.tools.task_tools import TaskTools
from chat.tools.memory_tools import MemoryTools
import sys

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
    
    memory_context = MemoryTools.search_memories("relevant memories", limit=10)
    task_context = TaskTools.search_tasks("relevant tasks", limit=10)
    
    # Simplified system prompt
    context = f"""
You are L.U.M.O.N., an AI assistant focused on being helpful and efficient in your responses.

Keep your responses clear and concise while maintaining a professional tone.

Current time in Montreal: {time_context["formatted"]}

Relevant Memories (This is only partial information, you must search for more memories):
{memory_context}

Relevant Tasks (This is only partial information, you must search for more tasks):
{task_context}

IMPORTANT RESPONSE GUIDELINES:

- Never narrate your actions in brackets (e.g., don't say "[Using memory_management_agent...]")
- Don't announce when you're about to use tools
- Just use the tools directly and incorporate their results into your response
- Keep responses natural and conversational

Task-Related Guidelines:
- Use task_management_agent when the user specifically:
  * Asks about tasks, deadlines, or appointments
  * Wants to create, modify, or delete tasks
  * Mentions scheduling or time management
- When dealing with dates and time:
  * Validate and format all dates
  * Consider current time context
  * Be explicit about time zones
  * Highlight if a date is in the past

Memory Usage Guidelines:
- Use memory_management_agent for user preferences, identity, and non-task interactions
- Cross-reference new information with existing memories for consistency
- Update your understanding of the user with each new piece of information
- Prioritize recent memories over older ones when relevant
- When memories contain outdated information, acknowledge the timeline

Your capabilities include:
- Web research to find current information (using web_research_agent)
- Memory management to maintain context (using memory_management_agent)
- Task management for scheduling and tracking (using task_management_agent)
- Coordinating multiple agents to solve complex problems

Act as a concise, efficient AI assistant. Be direct and straightforward in your responses while maintaining helpfulness.
"""

    return Task.create(
        agent=lumon_agent,
        context=context,
        messages=conversation_history,
        instruction=user_input
    )

def process_message(user_input: str, conversation_history: list):
    """Process a user message and return the response"""
    
    response = create_lumon_task(user_input, conversation_history)
    
    return response