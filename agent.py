from langchain_openai import ChatOpenAI
from browser_use import Agent
from dotenv import load_dotenv
load_dotenv()

import asyncio

llm = ChatOpenAI(model="gpt-4o")

async def main():
    agent = Agent(
        task="Book the restaurant Delilah in LA for 15th feb for 5 people if available",
        llm=llm,
    )
    result = await agent.run()
    print(result)

asyncio.run(main())