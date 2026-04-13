import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import asynccontextmanager
from fastapi.responses import StreamingResponse

from ollama import chat
from ollama import ChatResponse
from ollama import AsyncClient

import sqlite3
import datetime
import calendar

from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings, StorageContext, load_index_from_storage
from llama_index.core.agent.workflow import AgentWorkflow
from llama_index.core.llms import ChatMessage
from llama_index.core.memory import ChatMemoryBuffer

from settings import load_settings, save_settings

############################
### Starting and closing ###
############################

@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    app.settings = settings
    app.memory = ChatMemoryBuffer.from_defaults(token_limit = 4_000)

    start_db()
    rows = load_previous_messages(True)
    append_to_history(rows)

    yield

    del app.settings
    del app.memory
    print("Closing app.")

app = FastAPI(lifespan = lifespan)

##############
### SQLite ###
##############

def append_to_history(rows):
    for message in rows:
        text = ChatMessage(
            role = message[0],
            content = message[1],
            additional_kwargs = {"timestamp": datetime.datetime.strptime(message[2], "%Y-%m-%d %H:%M:%S.%f")}
        )
        app.memory.put(text)

def get_db():
    connection = sqlite3.connect("chat_history.db")
    return connection

def start_db(): # -> not async because i actually want the program to not continue until the db is created.
    # Defining the database
    connection = get_db()
    cursor = connection.cursor()

    # Creating the table
    try:
        with connection:
            table_create = """CREATE TABLE IF NOT EXISTS
            messages(id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, message TEXT, timedate TEXT)"""

            cursor.execute(table_create)
    except Exception as e:
        print("DB Error: ", e)
    finally:
        connection.close()

async def insert_into_db(role, message, timestamp):
    connection = get_db()
    cursor = connection.cursor()

    try:
        with connection:
            cursor.execute("INSERT INTO messages (role, message, timedate) VALUES (?, ?, ?);", (role, message, timestamp))
    except Exception as e:
        print("DB Error: ", e)
    finally:
        connection.close()

def load_previous_messages(use_limit: bool = True):
    # Execute a grab the latest N messages and put them in memory
    connection = get_db()
    cursor = connection.cursor()

    try:
        if use_limit == True:
            cursor.execute(
                "SELECT role, message, timedate FROM messages ORDER BY id DESC LIMIT ?",
                (app.settings["Global"]["max_history"], )
            )

            rows = cursor.fetchall()

            return rows[::-1]
        else:
            cursor.execute(
                "SELECT role, message, timedate FROM messages ORDER BY id ASC"
            )
            rows = cursor.fetchall()
            return rows
    except Exception as e:
        print("DB Error: ", e)
        return []
    finally:
        connection.close()

@app.post("/api/get-old-texts")
async def reset_get_old_texts():
    app.chat_retrieval_index = -1

    return {"response": "OK!"}

@app.get("/api/get-old-texts")
async def get_old_texts():
    connection = get_db()
    cursor = connection.cursor()
    max_texts = 20

    if app.chat_retrieval_index == -1:
        idx = cursor.execute("SELECT id FROM messages ORDER BY id DESC LIMIT 1").fetchone()
        if idx == None:
            return {"response": []}
        
        idx = idx[0]
        app.chat_retrieval_index = idx - max_texts if (idx - max_texts >= 0) else 0

    elif app.chat_retrieval_index > 0:
        idx = app.chat_retrieval_index
        app.chat_retrieval_index = max(0, app.chat_retrieval_index - max_texts)
    else:
        return {"response": []}
    
    print(f"LOG Chat retrieval index: {app.chat_retrieval_index}")

    if app.chat_retrieval_index >= 0:
        try:
            with connection:
                twenty_texts = cursor.execute(
                    "SELECT role, message, timedate FROM messages WHERE id <= ? ORDER BY id DESC LIMIT ?;",
                    (idx, max_texts)
                ).fetchall()[::-1]
            reply_json = {
                "response": twenty_texts
            }
            return reply_json

        except Exception as e:
            print("DB Error: ", e)
        finally:
            connection.close()

#################
### Variables ###
#################

app.settings = {
    "Model": {
        "model_name": "qwen3.5:9b",
        "reasoning": False,
        "streaming": True
    },
    "Global": {
        "max_history": 10,
    }
}

class UserText(BaseModel):
    user_text: str

class options(BaseModel):
    option_name: str
    option: bool|str

###########
### RAG ###
###########

# embedding_context_window = 8_192
llm_context_window = 8_192

embedding_model = OllamaEmbedding(
    model_name = "nomic-embed-text:latest"
)
Settings.llm = Ollama(
    model = app.settings["Model"]["model_name"],
    request_timeout = 360.0,
    context_window = llm_context_window
)

try:
    docs = SimpleDirectoryReader("data").load_data() # Loads the folder and the inner data
except Exception as e:
    print(f"No docs found!")
    docs = []

index = VectorStoreIndex.from_documents( # Apparently just says "here are the docs, the embed model will work on it"
    docs,
    embed_model = embedding_model
)
index.storage_context.persist("storage") # Says "hey, we already found the stuff, don't search again"
storage_context = StorageContext.from_defaults(persist_dir = "storage")
index = load_index_from_storage( # Loads the already found things if there are any
    storage_context,
    embed_model = embedding_model
)

query_engine = index.as_query_engine( # Connects what the embed model found to the llm
    llm = Settings.llm
)

# async def search_docs(query: str): # Function that says to the model "wait, let me search here based on what the user's asking"
#     response = await query_engine.aquery(query)
#     return str(response)

# agent = AgentWorkflow.from_tools_or_functions(
#     [search_docs],
#     llm = Settings.llm,
#     # system_prompt = 
# )


#############################
### Send and receive text ###
#############################

async def stream_reply(chat_history):
    """
    Function that just yields the chunk for the streaming response to work.
    """
    response = await Settings.llm.astream_chat(
        messages = chat_history
    )
    async for chunk in response:
        yield chunk.delta

@app.post("/api/send-text")
async def send_text(text: UserText):
    current_datetime = datetime.datetime.now()
    prev_history = app.memory.get()
    if len(prev_history) > 0:
        latest_datetime = prev_history[-1].additional_kwargs["timestamp"]
    else:
        latest_datetime = current_datetime
    
    last_seen = current_datetime - latest_datetime
    week_day = calendar.day_name[current_datetime.weekday()]

    message = ChatMessage(role = "user", content = text.user_text, additional_kwargs = {"timestamp": current_datetime})
    system_prompt = ChatMessage(
        role = "system",
        content = f"""
            You are a friendly AI assistant.
            One of the main things you should know is the latest text was from this date time: {str(latest_datetime)},
            meanwhile the current text you're receiving is from {str(current_datetime)},
            time elapsed from latest message is {str(last_seen)} or {str(last_seen.days)}, which is {str(week_day)}.
        """
    )

    await insert_into_db("user", str(text.user_text), str(current_datetime))

    app.memory.put(message)

    history = app.memory.get()

    complete_history = [system_prompt] + history

    print(f"Complete history: {complete_history}")

    match app.settings["Model"]["streaming"]:
        case "on":
            return StreamingResponse(stream_reply(complete_history), media_type = "text/event-stream")

        case "off":
            response: ChatResponse = Settings.llm.chat(
                messages = complete_history # chat_history
            )

            assistant_timedate = datetime.datetime.now()
            assistant_message = ChatMessage(
                role = "assistant",
                content = response.message.content, # No need to give the thinking process tbh.
                additional_kwargs = {"timestamp": assistant_timedate}
            )

            await insert_into_db("assistant", str(response.message.content), str(assistant_timedate))

            # NOTE: Check if the model thought.

            app.memory.put(assistant_message)

            return {"status": "success", "response": response.message.content, "thinking": None}

@app.post("/api/save-assistant-text")
async def append_streamed_text(text: UserText):
    """
    Easiest solution to append the streaming text.
    """
    assistant_text = text.user_text
    assistant_timedate = datetime.datetime.now()
    assistant_message = ChatMessage(
        role = "assistant",
        content = assistant_text,
        additional_kwargs = {"timestamp": assistant_timedate}
    )

    await insert_into_db("assistant", str(assistant_text), str(assistant_timedate))

    app.memory.put(assistant_message)

################
### Settings ###
################

@app.post("/api/change-settings")
async def settings(option: options):
    """
    Just sets the variables in the app.variable, then calls the actual function to save the settings as file.
    """

    match option.option_name:
        case "model_name":
            app.settings["Model"]["model_name"] = option.option
        case "reasoning":
            if option.option == "False":
                option.option = False
            app.settings["Model"]["reasoning"] = option.option
        case "streaming":
            if option.option == "on":
                app.settings["Model"]["streaming"] = "on"
            else:
                app.settings["Model"]["streaming"] = "off"

    # NOTE: There's no Global -> max_history here for now!

    save_settings(app.settings)

    return {"status": "success"}

@app.get("/api/load-settings")
def get_settings():
    """
    Just a getter.
    """
    return app.settings


#############################
### Mount and starting up ###
#############################

app.mount("/", StaticFiles(directory = "src/html", html = True), name = "static")

if __name__ == "__main__":
    uvicorn.run("main:app", host = "0.0.0.0", port = 8000, reload = True)
