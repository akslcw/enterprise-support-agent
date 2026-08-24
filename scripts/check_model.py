from app.llm import create_chat_model


model = create_chat_model()
response = model.invoke("请只回复：模型连接成功")

print(response.content)