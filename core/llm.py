import os
from dotenv import load_dotenv
from langchain_groq import ChatGroq

load_dotenv()


# FEEELING LIKE A FREELOADER :)


# HuggingFaceEndpoint from LANGCHAIN 
# model = HuggingFaceEndpoint(
#     repo_id="google/gemma-3-27b-it",
#     task="text-generation",
#     max_new_tokens=512,
#     temperature=0.1,
#     huggingfacehub_api_token=os.getenv("HUGGINGFACEHUB_API_TOKEN"),
# )
# llm = ChatHuggingFace(llm=model)


# CHATNVIDIA FROM  NVIDIA NMI VIA LANGCHAIN
# llm = ChatNVIDIA(
#   model="meta/llama-3.3-70b-instruct",
#   api_key=os.getenv("NVIDIA_API_KEY"), 
#   temperature=0.1,
#   top_p=0.7,
#   max_tokens=1024,
# )


# Production-grade Groq LLM configuration
MODEL_NAME = os.getenv("LLM_MODEL_NAME", "openai/gpt-oss-120b")
TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.1"))

llm = ChatGroq(
    model=MODEL_NAME,
    temperature=TEMPERATURE,
)


