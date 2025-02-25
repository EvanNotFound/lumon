from langchain_community.tools import TavilySearchResults

search = TavilySearchResults(max_results=1)

def search_tavily(query: str) -> str:
    """Search the web for information"""
    return search.invoke(query)
