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
        agent_executor = create_chat_chain()
        
        while True:
            user_input = input("\nYou: ").strip()
            
            if user_input.lower() in ["exit", "quit", "bye", "goodbye"]:
                print("\nJ.A.R.V.I.S.: Goodbye, Sir!")
                break
                
            if not user_input:
                print("Please say something!")
                continue
                
            try:
                response = agent_executor.invoke({"input": user_input})
                print(f"\nJ.A.R.V.I.S.: {response['output']}")
                
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
