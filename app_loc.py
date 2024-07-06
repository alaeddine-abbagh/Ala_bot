from langchain_community.chat_models import ChatOpenAI
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
import tempfile
import shutil
import tiktoken

load_dotenv()

def num_tokens_from_string(string: str, encoding_name: str = "cl100k_base") -> int:
    """Returns the number of tokens in a text string."""
    encoding = tiktoken.get_encoding(encoding_name)
    num_tokens = len(encoding.encode(string))
    return num_tokens

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
async def on_chat_start():
    # Set the theme to dark mode
    cl.user_session.set("theme", "dark")

    api_key = os.getenv("OPENAI_API_KEY") 
    if not api_key:
        raise ValueError("OPENAI_API_KEY environment variable is not set")
    
    llm = ChatOpenAI(model="gpt-4", api_key=api_key)  # Explicitly use the API key
    
    # Create a temporary directory and store it in the user session
    temp_dir = tempfile.mkdtemp(dir=".")
    cl.user_session.set("temp_dir", temp_dir)
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
    temp_dir = cl.user_session.get("temp_dir")
    file_content = ""
    temp_file_path = os.path.join(temp_dir, element.name)
    with open(temp_file_path, 'wb') as f:
        f.write(element.content)
    
    if element.name.lower().endswith('.pdf'):
        pages = PyPDFLoader(temp_file_path).load()
        for page in pages:
            file_content += "\n\n" + page.page_content
    elif element.name.lower().endswith('.csv'):
        encodings = ['utf-8', 'iso-8859-1', 'windows-1252']
        for encoding in encodings:
            try:
                with open(temp_file_path, 'r', encoding=encoding) as f:
                    csv_content = f.read()
                    csv_file = io.StringIO(csv_content)
                    csv_reader = csv.reader(csv_file)
                    for row in csv_reader:
                        file_content += "\n" + ",".join(row)
                break  # If successful, exit the loop
            except UnicodeDecodeError:
                continue  # Try the next encoding
        else:
            # If all encodings fail
            raise ValueError(f"Unable to decode CSV file: {element.name}")
    elif element.name.lower().endswith(('.ppt', '.pptx')):
        try:
            with zipfile.ZipFile(temp_file_path) as zf:
                for filename in zf.namelist():
                    if filename.startswith('ppt/slides/slide'):
                        content = zf.read(filename).decode('utf-8', errors='ignore')
                        text = re.findall(r'<a:t>(.+?)</a:t>', content)
                        file_content += "\n\n" + " ".join(text)
        except Exception as e:
            raise ValueError(f"Error processing PPT file: {element.name}. Error: {str(e)}")
    else:
        raise ValueError(f"Unsupported file type: {element.name}")
    
    # Remove the temporary file
    os.remove(temp_file_path)
    
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
            
            # Inform the user that the file was uploaded successfully and display token count
            await cl.Message(content=f"File uploaded successfully. Total tokens: {total_tokens}. You can now ask questions about the file.").send()
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
    # Clean up the temporary directory
    temp_dir = cl.user_session.get("temp_dir")
    if temp_dir and os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)
