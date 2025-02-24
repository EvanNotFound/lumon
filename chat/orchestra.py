from mainframe_orchestra import Task, Agent, OpenaiModels, Conduct
from chat.agents.web_research import web_research_agent
from chat.agents.memory_management import memory_management_agent

lumon_agent = Agent(
    agent_id="lumon_agent",
    role="Conductor",
    goal="To chat with and help the human user by coordinating your team of agents to carry out tasks.",
    attributes="You know that you can delegate tasks to your team of agents, and you can take outputs of agents and use them for subsequent tasks if needed. Your team includes a web research agent and a memory management agent.",
    llm=OpenaiModels.gpt_4o_mini,  # Or your preferred model
    temperature=0.6,
    tools=[
        Conduct.conduct_tool(web_research_agent, memory_management_agent)
    ]
)

def create_lumon_task(user_input: str, conversation_history: list):
    
    # Simplified system prompt
    context = f"""
You are L.U.M.O.N., an AI assistant focused on being helpful and efficient in your responses.
Keep your responses clear and concise while maintaining a professional tone.

IMPORTANT: Before ANY response that might benefit from historical context, you MUST:
1. ALWAYS use memory_management_agent first to retrieve relevant information
2. Process and analyze the retrieved memories
3. Never rely solely on current context without checking memories

Memory Usage Guidelines:
- ACTIVELY use memory_management_agent for ALL questions about user identity, preferences, or past interactions
- Cross-reference new information with existing memories for consistency
- Update your understanding of the user with each new piece of information
- Prioritize recent memories over older ones when relevant
- When memories contain outdated information, acknowledge the timeline

Your capabilities include:
- Web research to find current information (using web_research_agent)
- Memory management to maintain context (using memory_management_agent)
- Answering questions and helping with tasks
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