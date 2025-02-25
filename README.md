# Lumon AI

Lumon is a personal AI assistant built with Python that provides a conversational interface with memory capabilities, task management, and web research functionality.

## Features

- **Conversational Interface**: Interact with Lumon through a natural language interface in your terminal
- **Memory Management**: Lumon remembers your preferences, identity, and past interactions
- **Task Management**: Create, track, and manage tasks, deadlines, and appointments
- **Web Research**: Search the web for information directly through the assistant
- **Rich Text Output**: Enhanced UI with markdown rendering in production mode
- **Orchestration System**: Uses a conductor-agent architecture to delegate specialized tasks

## Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/lumon.git
   cd lumon
   ```

2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your API keys:
   ```
   OPENAI_API_KEY=your_openai_api_key
   OPENROUTER_API_KEY=your_openrouter_api_key
   GEMINI_API_KEY=your_gemini_api_key
   ANONYMIZED_TELEMETRY=false

   CHROME_INSTANCE_PATH=your_chrome_instance_path (eg /Applications/Chromium.app/Contents/MacOS/Chromium)
   ```

## Usage

Run Lumon in standard mode:
```bash
python main.py
```

Run Lumon in production mode with enhanced UI:
```bash
python main.py --prod
```
or
```bash
python main.py -p
```

## Project Structure

- `main.py`: Entry point for the application
- `chat/`: Contains the core chat functionality
  - `orchestra.py`: Orchestrates the chat system and agent interactions
  - `agents/`: Specialized agents for different tasks
    - `web_research.py`: Agent for web search functionality
    - `memory_management.py`: Agent for managing user memories
    - `task_management.py`: Agent for managing tasks and appointments
  - `tools/`: Tools used by the agents
    - `memory_tools.py`: Tools for memory operations
    - `task_tools.py`: Tools for task management
    - `date_tool.py`: Tools for date handling
    - `calculation.py`: Tools for calculations
    - `weather_tool.py`: Tools for weather information
- `config/`: Configuration files
  - `prompts.yaml`: System prompts for the AI assistant
- `utils/`: Utility functions and helpers
- `data/`: Storage for application data

## Dependencies

Lumon relies on several key libraries:
- `mainframe-orchestra`: For agent orchestration
- `langchain`: For language model interactions
- `openai`: For GPT model access
- `rich`: For enhanced terminal output
- `click`: For command-line interface
- `pandas`: For data manipulation
- `tiktoken`: For token counting

## License

This project is licensed under the terms included in the LICENSE file.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
