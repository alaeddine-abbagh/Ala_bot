from langchain_community.chat_models import ChatOpenAI
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain.schema import StrOutputParser
from langchain.chains import LLMChain
from langchain.memory import ConversationBufferMemory
from langchain_community.document_loaders import PyPDFLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from dotenv import load_dotenv
import os
import logging
import csv
import io
import zipfile
import re
import chainlit as cl
import tempfile
import shutil
import tiktoken
import httpx
from httpx_auth import OAuth2ClientCredentials
from openai import AzureOpenAI

load_dotenv()

def num_tokens_from_string(string: str, encoding_name: str = "cl100k_base") -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

async def summarize_file(file_content: str) -> str:
    llm = cl.user_session.get("llm")
    
    # Split the content into chunks
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=4000,
        chunk_overlap=200,
        length_function=len,
    )
    chunks = text_splitter.split_text(file_content)
    
    # Summarize each chunk
    summaries = []
    for chunk in chunks:
        prompt = ChatPromptTemplate.from_template(
            "Please provide a concise summary of the following text chunk:\n\n{chunk}"
        )
        chain = prompt | llm | StrOutputParser()
        summary = await chain.ainvoke({"chunk": chunk})
        summaries.append(summary)
    
    # Combine summaries
    combined_summary = "\n\n".join(summaries)
    
    # Create a final summary
    final_prompt = ChatPromptTemplate.from_template(
        "Please provide a concise overall summary of the following summaries:\n\n{summaries}"
    )
    final_chain = final_prompt | llm | StrOutputParser()
    final_summary = await final_chain.ainvoke({"summaries": combined_summary})
    
    return final_summary
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
async def on_chat_start():
    # Set the theme to dark mode
    cl.user_session.set("theme", "dark")

    llm = ChatOpenAI(model="gpt4o", client = client.chat.completions, api_key = "FAKE_KEY")
    
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

async def process_file(element):
    file_content = ""
    
    if element.name.lower().endswith('.pdf'):
        pdf_content = element.content
        pdf_file = io.BytesIO(pdf_content)
        pages = PyPDFLoader(pdf_file).load()
        for page in pages:
            file_content += "\n\n" + page.page_content
    elif element.name.lower().endswith('.csv'):
        csv_content = element.content.decode('utf-8')
        csv_file = io.StringIO(csv_content)
        csv_reader = csv.reader(csv_file)
        for row in csv_reader:
            file_content += "\n" + ",".join(row)
    elif element.name.lower().endswith(('.ppt', '.pptx')):
        try:
            with zipfile.ZipFile(io.BytesIO(element.content)) as zf:
                for filename in zf.namelist():
                    if filename.startswith('ppt/slides/slide'):
                        content = zf.read(filename).decode('utf-8', errors='ignore')
                        text = re.findall(r'<a:t>(.+?)</a:t>', content)
                        file_content += "\n\n" + " ".join(text)
        except Exception as e:
            raise ValueError(f"Error processing PPT file: {element.name}. Error: {str(e)}")
    else:
        raise ValueError(f"Unsupported file type: {element.name}")
    
    # Count tokens
    token_count = num_tokens_from_string(file_content)
    
    return file_content, token_count



@cl.on_message
async def on_message(message: cl.Message):
    content = message.content
    temp_dir = cl.user_session.get("temp_dir")
    file_content = cl.user_session.get("file_content", "")

    if message.elements:
        try:
            total_tokens = 0
            for element in message.elements:
                processed_content, token_count = await process_file(element)
                file_content += processed_content
                total_tokens += token_count
            
            # Store the file content in the user session
            cl.user_session.set("file_content", file_content)
            
            # Give the user options after file upload
            actions = [
                cl.Action(name="summarize", value="summarize", label="Summarize File"),
                cl.Action(name="do_nothing", value="do_nothing", label="Do Nothing")
            ]
            res = await cl.AskActionMessage(
                content=f"File uploaded successfully. Total tokens: {total_tokens}. What would you like to do?",
                actions=actions
            ).send()

            if res:
                if res.get("value") == "summarize":
                    summary = await summarize_file(file_content)
                    await cl.Message(content=f"Summary of the file:\n\n{summary}").send()
                elif res.get("value") == "do_nothing":
                    await cl.Message(content="Alright, no action taken. You can now ask questions about the file.").send()
            return
        except ValueError as e:
            await cl.Message(content=str(e)).send()
            return

    if content:
        # Always include the file content with the question
        full_content = f"Voici le document:\n{file_content}\n\nVoici la question de l'utilisateur:\n{content}"
        
        llm = cl.user_session.get("llm")
        prompt = cl.user_session.get("prompt")
        memory = cl.user_session.get("memory")
        conversation = LLMChain(
            llm=llm,
            prompt=prompt,
            verbose=True,
            memory=memory
        )
        response = conversation.predict(question=full_content)
        await cl.Message(content=response).send()

@cl.on_chat_end
async def on_chat_end():
    # Clean up any resources if needed
    pass
