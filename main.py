# main.py
import sys
from langchain.schema import HumanMessage, SystemMessage
from chat.chain import create_chat_chain

def main():
    print("\n" + "="*50)
    print("Initializing J.A.R.V.I.S. - Personal AI Assistant")
    print("All systems are online and operational.")
    print("="*50 + "\n")
    
    try:
        chat, system_prompt = create_chat_chain()
        messages = [SystemMessage(content=system_prompt)]
        
        while True:
            user_input = input("\nYou: ").strip()
            
            if user_input.lower() in ["exit", "quit", "bye", "goodbye"]:
                print("\nJ.A.R.V.I.S.: Powering down systems. Have a wonderful day. Do let me know if you need anything else.")
                break
                
            if not user_input:
                print("Please say something!")
                continue
                
            try:
                # Add user message to context
                messages.append(HumanMessage(content=user_input))
                
                # Get streaming response
                print("\nAssistant: ", end="", flush=True)
                response_content = ""
                for chunk in chat.stream(messages).tool_calls:
                    content_chunk = chunk.content
                    print(content_chunk, end="", flush=True)
                    response_content += content_chunk
                print()  # New line after response
                
                # Add assistant response to context
                messages.append(HumanMessage(content=response_content))
                
                # Keep context window manageable (last 5 exchanges)
                if len(messages) > 11:  # system prompt + 5 exchanges (2 messages each)
                    messages = [messages[0]] + messages[-10:]
                    
            except Exception as e:
                print(f"\nOops! Something went wrong: {str(e)}")
                print("Please try again!")
                
    except KeyboardInterrupt:
        print("\n\nGoodbye! Have a great day!")
    except Exception as e:
        print(f"\nFatal error: {str(e)}")
        return 1
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
