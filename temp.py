from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain.schema import Document

sample_texts = [
    "This is the first sample text.",
    "Here is another piece of text.",
    "This text is for testing the vector store."
]

# Convert texts to Documents
documents = [Document(page_content=text) for text in sample_texts]

# Create embeddings instance
embeddings = OpenAIEmbeddings()

# Create FAISS from documents (this is the correct way to initialize)
vector_store = FAISS.from_documents(documents, embeddings)

# Save the vector store
vector_store.save_local("data/memory_store")