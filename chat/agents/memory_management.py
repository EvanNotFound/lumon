from mainframe_orchestra import Agent, OpenaiModels
from chat.tools.memory_tools import MemoryTools

# Initialize the memory tools
MemoryTools()

memory_management_agent = Agent(
    agent_id="memory_management_agent",
    role="Memory Management Agent",
    goal="Use your tools to manage memories, always try to remove duplicates and outdated memories, and consolidate similar memories into a single memory if necessary.",
    attributes="You can assist with memory tasks. Currently, you can save, delete, and update memories.",
    temperature=0.6,
    llm=OpenaiModels.gpt_4o_mini,
    tools=[MemoryTools.save_memory, MemoryTools.search_memories, MemoryTools.delete_memory, MemoryTools.update_memory]
)