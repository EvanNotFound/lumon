# weather_tool.py
import requests
from langchain.agents import Tool

def get_weather(location: str) -> str:
    # You could call an actual weather API, e.g., OpenWeatherMap
    # For simplicity, let's just pretend we return a dummy response
    return f"The current weather in {location} is sunny, 25°C."

weather_tool = Tool(
    name="WeatherTool",
    description="Use this tool to get weather information for a given location",
    func=get_weather
)
