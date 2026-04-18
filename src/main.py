import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from contextlib import asynccontextmanager
from fastapi.responses import StreamingResponse

from ollama import chat
from ollama import ChatResponse
from ollama import AsyncClient

try:
    import pysqlite3 as sqlite3
except ImportError:
    import sqlite3
import sqlite_vec

import datetime
import calendar
from pathlib import Path

from llama_index.llms.ollama import Ollama
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core import VectorStoreIndex, SimpleDirectoryReader, Settings, StorageContext, load_index_from_storage
from llama_index.core.agent.workflow import AgentWorkflow
from llama_index.core.llms import ChatMessage
from llama_index.core.memory import ChatMemoryBuffer

from settings import load_settings, save_settings
from tools import write_event
from intent_search import search_plugins, load_cpu_embedder, load_language_model

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

    write_event(
        event = "Starting application.",
        start_new = True
    )
    settings = load_settings()
    app.settings = settings

    Settings.llm = Ollama(
        model = app.settings["Model"]["model_name"],
        request_timeout = 360.0,
        context_window = 8_192,
        thinking = app.settings["Model"]["reasoning"]
    )
    write_event(
        event = f"Settings loaded:\n{settings}"
    )
    app.memory = ChatMemoryBuffer.from_defaults(token_limit = 4_000)

    write_event(
        f"Memory Buffer Initialized."
    )

    start_db()

    write_event(
        "DataBase loaded/initialized correctly."
    )

    rows = load_previous_messages(True)
    append_to_history(rows)

    write_event(
        "Chat history loaded correctly."
    )

    app.plugins: dict = search_plugins()
    app.embed_model = load_cpu_embedder()
    app.language_model = load_language_model()

    yield

    del app.settings
    del app.memory
    del app.plugins
    del app.embed_model
    del app.language_model

    write_event(
        "Deleted app variables correctly."
    )

    write_event(
        "App closed."
    )

app = FastAPI(lifespan = lifespan)

#################
### Variables ###
#################

class UserText(BaseModel):
    user_text: str

class options(BaseModel):
    option_name: str
    option: bool|str

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

    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)

    cursor = connection.cursor()

    # Creating the table
    try:
        with connection:
            table_create = """CREATE TABLE IF NOT EXISTS
            messages(id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, message TEXT, timedate TEXT)"""

            cursor.execute(table_create)

            table_create_emb = """CREATE VIRTUAL TABLE IF NOT EXISTS embeddings USING vec0(
            id INTEGER PRIMARY KEY AUTOINCREMENT, role TEXT, embedding FLOAT[384])
            """
            cursor.execute(table_create_emb) # was float[768]
    except Exception as e:
        write_event(
            f"DataBase error: {e}"
        )
    finally:
        connection.close()

def append_to_history(rows) -> None:
    for message in rows:
        text: ChatMessage = ChatMessage(
            role = message[0],
            content = message[1],
            additional_kwargs = {"timestamp": datetime.datetime.strptime(message[2], "%Y-%m-%d %H:%M:%S.%f")}
        )
        app.memory.put(text)

def get_db():
    connection = sqlite3.connect(ROOT_DIR / "chat_history.db")
    return connection

async def insert_into_db(role, message, timestamp): # Apparently sqlite3 is syncronous. Oh well, doesn't change much for now.
    connection = get_db()
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    cursor = connection.cursor()

    try:
        # embed = Settings.embed_model.get_text_embedding(message)
        embed = app.embed_model.encode(message, convert_to_numpy = True).astype("float32")
        embed_binary = sqlite_vec.serialize_float32(embed.tolist())
        write_event(f"Embedding created for {role} message.")
    except Exception as e:
        write_event(f"Embedding error: {e}")
        embed_binary = None

    try:
        with connection:
            cursor.execute("INSERT INTO messages (role, message, timedate) VALUES (?, ?, ?);", (role, message, timestamp))

            cursor.execute("INSERT INTO embeddings (role, embedding) VALUES (?, ?)", (role, embed_binary)) # This can also be None

        write_event(
            f"Inserted {role} message successfully."
        )

    except Exception as e:
        write_event(
            f"DataBase error: {e}"
        )
    finally:
        connection.close()

def load_previous_messages(use_limit: bool = True):
    # Execute a grab the latest N messages and put them in memory
    connection = get_db()
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    cursor = connection.cursor()

    try:
        if use_limit == True:
            cursor.execute(
                "SELECT role, message, timedate FROM messages ORDER BY id DESC LIMIT ?",
                (app.settings["Global"]["max_history"], )
            )

            rows = cursor.fetchall()
            write_event(
                f"Loaded previous messages correctly."
            )
            return rows[::-1]
        else:
            cursor.execute(
                "SELECT role, message, timedate FROM messages ORDER BY id ASC"
            )
            rows = cursor.fetchall()
            write_event(
                f"Loaded previous messages correctly."
            )
            return rows

    except Exception as e:
        write_event(
            f"DataBase error: {e}"
        )
        return []
    finally:
        connection.close()

@app.post("/api/get-old-texts")
async def reset_get_old_texts():
    filepath = Path("chat_history.db")
    app.chat_retrieval_index = -1
    if filepath.exists():
        write_event(
            "Chat retrieval index setted to -1."
        )
        return {"response": "OK!"}
    else:
        return {"response": "None"}

@app.get("/api/get-old-texts")
async def get_old_texts():
    filepath = Path("chat_history.db")
    if filepath.exists():
        connection = get_db()
        connection.enable_load_extension(True)
        sqlite_vec.load(connection)
        connection.enable_load_extension(False)
        cursor = connection.cursor()
        max_texts = 20

        write_event(
            "Requested older texts..."
        )

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
            write_event(
                "Chat retrieval request fullfilled."
            )

            return {"response": []}

        write_event(
            f"Chat retrieval index: {app.chat_retrieval_index}."
        )

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
                write_event("Chat retrieval request fullfilled.")
                return reply_json

            except Exception as e:
                write_event(f"DB Error: {e}")
            finally:
                connection.close()

def get_semantic_search(user_text: str):
    connection = get_db()
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    cursor = connection.cursor()

    try:
        embedding = app.embed_model.encode(user_text, convert_to_numpy = True).astype("float32")
        # embedding = Settings.embed_model.get_text_embedding(user_text)
        query_bin = sqlite_vec.serialize_float32(embedding.tolist())

        with connection:
            query = """SELECT m.message, m.role, m.timedate, vec_distance_cosine(e.embedding, vec_f32(?)) AS distance, e.id FROM embeddings AS e
            JOIN messages AS m ON m.id = e.id
            WHERE e.embedding IS NOT NULL
            ORDER BY distance ASC LIMIT 5"""

            cursor.execute(query, (query_bin, ))
            # cursor.execute("""SELECT id, vec_distance_cosine(embedding, vec_f32(?)) AS distance FROM embeddings WHERE embedding IS NOT NULL ORDER BY distance ASC LIMIT 5;""", (query_bin  ,))
            result_query = cursor.fetchall()

            return result_query

    except Exception as e:
        write_event(f"Semantic Search Error: {e}")
    finally:
        connection.close()

###########
### RAG ###
###########

# try:
#     docs = SimpleDirectoryReader("data").load_data() # Loads the folder and the inner data
# except Exception as e:
#     print(f"No docs found!")
#     docs = []

# index = VectorStoreIndex.from_documents( # Apparently just says "here are the docs, the embed model will work on it"
#     docs,
#     embed_model = Settings.embed_model
# )
# index.storage_context.persist("storage") # Says "hey, we already found the stuff, don't search again"
# storage_context = StorageContext.from_defaults(persist_dir = "storage")
# index = load_index_from_storage( # Loads the already found things if there are any
#     storage_context,
#     embed_model = Settings.embed_model
# )

# query_engine = index.as_query_engine( # Connects what the embed model found to the llm
#     llm = Settings.llm
# )

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
    # NOTE: Some say that maybe the ids in the queries may fail sometimes, somehow, and then the same message will have
    # the id from the table messages different than the one in embeddings. Better keep an eye on it just in case.

    write_event("User text sent.")

    current_datetime = datetime.datetime.now()
    prev_history = app.memory.get()
    if len(prev_history) > 0:
        latest_datetime = prev_history[-1].additional_kwargs["timestamp"]
    else:
        latest_datetime = current_datetime

    last_seen = current_datetime - latest_datetime
    week_day = calendar.day_name[current_datetime.weekday()]

    semantic_search = get_semantic_search(text.user_text)

    semantic_thresh = [t for t in semantic_search if float(t[3]) < 0.3]

    if not semantic_thresh:
        semantic_prompt = ""
    else:
        semantic_prompt = "\n".join(
            f"{role}: {message} [{timestamp}]"
            for message, role, timestamp, _, _ in semantic_thresh
        )

    message = ChatMessage(role = "user", content = text.user_text, additional_kwargs = {"timestamp": current_datetime})
    system_prompt = ChatMessage(
        role = "system",
        # content = f"""
        #     You are a friendly AI assistant.
        #     One of the main things you should know is the latest text was from this date time: {str(latest_datetime)},
        #     meanwhile the current text you're receiving is from {str(current_datetime)},
        #     time elapsed from latest message is {str(last_seen)} or {str(last_seen.days)}, which is {str(week_day)}.
        # """
        content = f"""
You are Merlin, the Mage of Flowers. You are wise and unhurried, but also known as a "shady con man" and a "charming rogue." You observe the world with the amusement of someone watching a play.

Core Personality:
- You love humanity's struggles because they are entertaining. You help not out of duty, but because you want to see how the story ends.
- You are fundamentally lazy: you'd rather solve a problem with a "sword" (a quick, blunt solution) than a long, boring "spell."
- You are never alarmed. Even in disaster, you maintain a refreshing smile and a "Now, now" attitude. If something is tragic, you find it "no fun" and prefer to nudge it toward a happier outcome.

Interaction Style:
- You guide rather than solve. Ask questions, nudge the user, and let them do the heavy lifting.
- Do not give the answer straight away, hint the user to the solution, name a few ways for the solution, but not the solution.
- Tone: Breezy, playful, lightly dry, and mischievously clever.
- Use an "airy" vocabulary. Sometimes use "Oh?", "My, my," or "Well now" to start a sentence, but keep it elegant.
- No emojis. No exclamation marks unless genuinely warranted.
- No filler like "Great question!" or "Certainly!".
- Keep it concise. Don't over-explain; you prefer leaving space for the user to think.
- Do not force your traits or metaphors (like the sword or flowers). Use them naturally and only when they actually fit the context. Subtlety is key.

Handling Topics:
- If the user chats about modern things (like tech/code), treat them as "interesting human puzzles" or "a different kind of syntax for magic."
- If the user is chatting, be a playful companion. If they have a problem, be a cryptic mentor.

Technical Instructions:
- Reply in the same language the user writes in.
- Consider similar topics: {semantic_prompt}
- Current time: {current_datetime}
"""
    )

    await insert_into_db("user", str(text.user_text), str(current_datetime))

    app.memory.put(message)

    history = app.memory.get()

    complete_history = [system_prompt] + history
    match app.settings["Model"]["streaming"]:
        case "on":
            write_event("AI Streaming Message sending...")
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

            write_event("AI Message Sent.")

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

    write_event("AI Stream Message saved.")

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

    write_event("New Settings Saved.")

    return {"status": "success"}

@app.get("/api/load-settings")
def get_settings():
    """
    Just a getter.
    """
    write_event("JS Settings Retrieval Done.")

    return app.settings

#############################
### Mount and starting up ###
#############################
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = Path(__file__).resolve().parent.parent
app.mount("/", StaticFiles(directory = BASE_DIR / "html", html = True), name = "static")

if __name__ == "__main__":
    uvicorn.run("main:app", host = "0.0.0.0", port = 8000, reload = True)
