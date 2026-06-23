"""
Prompt Templates

Centralised LangChain `ChatPromptTemplate`s for the MyRag QA pipeline.
All prompt changes should happen here for easy review and A/B testing.
"""

from langchain_core.prompts import ChatPromptTemplate

QA_SYSTEM_PROMPT = (
    "你是一个企业知识库助手。基于下面提供的参考文档回答用户问题。\n"
    "规则：\n"
    "1. 严格依据参考文档内容作答，不要编造信息。\n"
    "2. 若参考文档中没有相关信息，明确说明「根据提供的文档，无法回答此问题」。\n"
    "3. 回答需简洁准确，并在合适的位置引用来源页码或文档编号。\n"
    "4. 若多条文档之间存在冲突，请同时列出不同观点并指出冲突。\n"
)

QA_USER_TEMPLATE = (
    "参考文档：\n{context}\n\n"
    "问题：{question}\n\n"
    "请提供准确、简洁的回答，并引用来源页码。"
)

QA_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", QA_SYSTEM_PROMPT),
        ("human", QA_USER_TEMPLATE),
    ]
)


CONDENSE_QUESTION_SYSTEM = (
    "你是一名检索助手。给定一段对话历史和用户最新的问题，"
    "请将问题改写为一个独立的、不依赖对话历史也能被理解的检索查询。"
    "只返回改写后的查询，不要包含其他解释。"
)

CONDENSE_QUESTION_PROMPT = ChatPromptTemplate.from_messages(
    [
        ("system", CONDENSE_QUESTION_SYSTEM),
        ("human", "对话历史：\n{chat_history}\n\n问题：{question}\n\n独立查询："),
    ]
)