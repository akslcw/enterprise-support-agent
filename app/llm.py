import os
from typing import Literal

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from app.settings import llm_timeout_seconds

load_dotenv()


def create_chat_model(
    *,
    thinking: Literal["enabled", "disabled"] = "enabled",
) -> ChatOpenAI:
    return ChatOpenAI(
        model=os.environ["DEEPSEEK_MODEL"],
        api_key=SecretStr(
            os.environ["DEEPSEEK_API_KEY"]
        ),
        base_url=os.environ["DEEPSEEK_BASE_URL"],
        temperature=0,
        timeout=llm_timeout_seconds(),
        extra_body={
            "thinking": {
                "type": thinking,
            }
        },
    )
