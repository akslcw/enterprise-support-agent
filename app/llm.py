import os

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


load_dotenv()


def create_chat_model() -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ["DEEPSEEK_MODEL"],
        api_key=os.environ["DEEPSEEK_API_KEY"],
        base_url=os.environ["DEEPSEEK_BASE_URL"],
        temperature=0,
    )