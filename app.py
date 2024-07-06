from langchain.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.schema import StrOutputParser
from langchain.schema.runnable import Runnable
from langchain.schema.runnable.config import RunnableConfig
from langchain.chains import LLMChain
import httpx
from httpx_auth import OAuth2ClientCredentials
from dotenv import load_dotenv
from openai import AzureOpenAI
import os
from langchain.memory import ConversationBufferMemory
from langchain_community.document_loaders import PyPDFLoader, CSVLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
import logging
import csv
import io

import chainlit as cl

load_dotenv()
OIDC_ENDPOINT = os.environ.get('OIDC_ENDPOINT')
OIDC_CLIENT_ID = os.environ.get('OIDC_CLIENT_ID')
OIDC_CLIENT_SECRET = os.environ.get('OIDC_CLIENT_SECRET')
OIDC_SCOPE = os.environ.get('OIDC_SCOPE')
APIGEE_ENDPOINT = os.environ.get('APIGEE_ENDPOINT')
AZURE_AOAI_API_VERSION = os.environ.get('AZURE_AOAI_API_VERSION')
MAPPING_PATH = os.environ.get("MAPPING_PATH")
UPLOAD_PATH = os.environ.get("UPLOAD_PATH")



def authenticate():
    oauth2_httpxclient=httpx.Client(verify=False)
    auth=OAuth2ClientCredentials(OIDC_ENDPOINT, client_id=OIDC_CLIENT_ID, client_secret=OIDC_CLIENT_SECRET, scope=OIDC_SCOPE,client=oauth2_httpxclient)
    client = AzureOpenAI(
    api_version=AZURE_AOAI_API_VERSION,
    azure_endpoint=APIGEE_ENDPOINT,
    api_key="FAKE_KEY",
    http_client=httpx.Client(auth=auth, verify=False))
    return client

client = authenticate()

# Set up logging for debugging purposes
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@cl.on_chat_start
def on_chat_start():
    llm = ChatOpenAI(model="gpt4o", client = client.chat.completions, api_key = "FAKE_KEY")
    memory = ConversationBufferMemory(memory_key="chat_history", return_messages=True)
    prompt = ChatPromptTemplate(
        messages=[
            SystemMessagePromptTemplate.from_template(
                """
                Tu es un assistant
                """
            ),
            # The `variable_name` here is what must align with memory
            MessagesPlaceholder(variable_name="chat_history"),
            HumanMessagePromptTemplate.from_template("{question}")
        ]
    )
    cl.user_session.set("llm", llm)
    cl.user_session.set("prompt", prompt)
    cl.user_session.set("memory", memory)

# Notice that we `return_messages=True` to fit into the MessagesPlaceholder
# Notice that `"chat_history"` aligns with the MessagesPlaceholder name.



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
                csv_content = element.content.decode('utf-8')
                csv_loader = CSVLoader(file_path=io.StringIO(csv_content))
                documents = csv_loader.load()
                for doc in documents:
                    file_content += "\n\n" + doc.page_content
            else:
                await cl.Message(content=f"Unsupported file type: {element.name}").send()
                return

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
