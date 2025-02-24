from mainframe_orchestra import Agent, OpenaiModels
from langchain_openai import OpenAIEmbeddings
from langchain.storage import LocalFileStore
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from chat.tools.memory_tools import MemoryTools

# Initialize the memory tools
MemoryTools()

memory_management_agent = Agent(
    agent_id="memory_management_agent",
    role="Memory Management Agent",
    goal="Use your tools to save and retrieve memories",
    attributes="You can assist with memory tasks, such as saving and retrieving memories using your tools",
    llm=OpenaiModels.gpt_4o_mini,
    tools=[MemoryTools.save_memory, MemoryTools.search_memories]
)