import asyncio

from langchain_core.messages import HumanMessage

from app.llm import create_chat_model
from app.supervisor import create_supervisor_node


CASES = [
    "订单 1002 到哪里了？",
    "退款审核通过后多久到账？",
    "帮我为客户 c-100 创建高优先级投诉工单",
    "北京今天天气怎么样？",
]


async def main() -> None:
    model = model = create_chat_model(thinking="disabled")
    supervisor = create_supervisor_node(model)

    for message in CASES:
        result = await supervisor(
            {
                "messages": [
                    HumanMessage(content=message),
                ]
            }
        )

        print(f"问题：{message}")
        print(f"路由：{result['next_agent']}")
        print()


if __name__ == "__main__":
    asyncio.run(main())