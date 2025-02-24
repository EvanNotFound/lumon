from mainframe_orchestra import Agent, OpenaiModels, WebTools
from browser_use import Agent as BrowserAgent
from langchain_openai import ChatOpenAI


# This Browser tool is a simple wrapper around the browser-use Agent, and will kick off the browser-use agent as a delegate.
class BrowserTools:
    @staticmethod
    async def browse_web(instruction: str) -> str:
        """Use browser-use to perform web browsing tasks
        
        Args:
            instruction (str): Web browsing task to execute, written in natural language
        
        Returns:
            str: Result of the executed browsing task
        """
        browser_agent = BrowserAgent(
            task=f"Browse the web and find information about {instruction}. Close cookies modals and other popups before using the page.",
            llm=ChatOpenAI(model="gpt-4o-mini"),
        )
        result = await browser_agent.run()
        return result


web_research_agent = Agent(
    agent_id="web_research_agent",
    role="Web Research Agent",
    goal="Use your web research tools to assist with the given task",
    attributes="You have expertise in web research and can use your tools to assist with the given task",
    llm=OpenaiModels.gpt_4o_mini,
    tools=[BrowserTools.browse_web]
)
