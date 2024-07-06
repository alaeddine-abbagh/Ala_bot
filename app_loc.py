from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.schema import StrOutputParser
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory
from langchain_community.document_loaders import PyPDFLoader, CSVLoader
from dotenv import load_dotenv
import os
import logging
import csv
import io
import zipfile
import re
import chainlit as cl

load_dotenv()

async def summarize_file(file_content: str) -> str:
    llm = cl.user_session.get("llm")
    prompt = ChatPromptTemplate.from_template(
        "Please provide a concise summary of the following document:\n\n{document}"
    )
    chain = prompt | llm | StrOutputParser()
    summary = await chain.ainvoke({"document": file_content})
    return summary

# Set up logging for debugging purposes
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@cl.on_chat_start
def on_chat_start():
    api_key = os.getenv("OPENAI_API_KEY") 
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    
    llm = ChatOpenAI(model="gpt-4", api_key=api_key)  # Explicitly use the API key
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    prompt = ChatPromptTemplate(
        messages=[
            SystemMessagePromptTemplate.from_template(
                """
                Tu es un assistant
                """
            ),
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessagePromptTemplate.from_template("{question}")
        ]
    )
    cl.user_session.set("llm", llm)
    cl.user_session.set("prompt", prompt)
    cl.user_session.set("memory", memory)

@cl.on_message
async def on_message(message: cl.Message):
    file_content = ""
    content = message.content
    if message.elements:
        for element in message.elements:
            if element.name.lower().endswith('.pdf'):
                pages = PyPDFLoader(element.path).load()
                for page in pages:
                    file_content += "\n\n" + page.page_content
            elif element.name.lower().endswith('.csv'):
                encodings = ['utf-8', 'iso-8859-1', 'windows-1252']
                for encoding in encodings:
                    try:
                        csv_content = element.content.decode(encoding)
                        csv_loader = CSVLoader(file_path=io.StringIO(csv_content))
                        documents = csv_loader.load()
                        for doc in documents:
                            file_content += "\n\n" + doc.page_content
                        break  # If successful, exit the loop
                    except UnicodeDecodeError:
                        continue  # Try the next encoding
                else:
                    # If all encodings fail
                    await cl.Message(content=f"Unable to decode CSV file: {element.name}").send()
                    return
            elif element.name.lower().endswith(('.ppt', '.pptx')):
                try:
                    with zipfile.ZipFile(io.BytesIO(element.content)) as zf:
                        for filename in zf.namelist():
                            if filename.startswith('ppt/slides/slide'):
                                content = zf.read(filename).decode('utf-8', errors='ignore')
                                text = re.findall(r'<a:t>(.+?)</a:t>', content)
                                file_content += "\n\n" + " ".join(text)
                except Exception as e:
                    await cl.Message(content=f"Error processing PPT file: {element.name}. Error: {str(e)}").send()
                    return
            else:
                await cl.Message(content=f"Unsupported file type: {element.name}").send()
                return

        # Add a button to summarize the file
        actions = [
            cl.Action(name="summarize", value="summarize", label="Summarize File")
        ]
        await cl.Message(content=f"File uploaded successfully. Would you like to summarize it?", actions=actions).send()
        
        # Wait for user action
        res = await cl.AskActionMessage(content="Choose an action:", actions=actions).send()
        if res and res.get("value") == "summarize":
            summary = await summarize_file(file_content)
            await cl.Message(content=f"Summary of the file:\n\n{summary}").send()

    if content:
        content = "Voici le document: " + file_content + "\nVoici la question de l'utilisateur:\n" + content
    llm = cl.user_session.get("llm")
    prompt = cl.user_session.get("prompt")
    memory = cl.user_session.get("memory")
    conversation = LLMChain(
        llm=llm,
        prompt=prompt,
        verbose=True,
        memory=memory
    )
    response = conversation.predict(question=content)
    await cl.Message(content=response).send()
