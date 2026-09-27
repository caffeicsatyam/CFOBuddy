import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()



# Production-grade Groq LLM configuration
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "openai/gpt-oss-120b")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))

llm = ChatGroq(
    model=MODEL_NAME,
    temperature=TEMPERATURE,
)


