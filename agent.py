from langchain_openai import ChatOpenAI
from browser_use import Agent
from dotenv import load_dotenv
load_dotenv()

import asyncio

llm = ChatOpenAI(model="gpt-4o")

async def main():
    agent = Agent(
        task="book a restaraunt for me in boston tonight for 2 people thats japanese and cheap at 9pm",
        llm=llm,
    )
    result = await agent.run()
    print(result)

asyncio.run(main())