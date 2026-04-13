# Merlin
Your AI assistant for your study and researching needs.

This tool gives you space to learn without having the solutions to the problems you'll face given to you easily, Merlin will help you organize your documents, research papers, and even your own notes!
It will also have a three-tier memory system: short-term (last n messages), mid-term (periodic summarization), long-term (vector RAG of full history).

## How does it work?
At the Core, Merlin is simple:

GUI:      HTML + CSS + JavaScript

Backend:  Python + FastAPI

AI:       Ollama + LlamaIndex

Memory:   SQLite

Merlin will not be always active (unless you tamper with Ollama yourself), and will sleep unless you text him, so your PC resources won't be a problem even if you leave him running.

## Current Features
As of now, Merlin it's in Early Stage of Development, he can:
- Stay totally local, so your private things won't be shared.
- Chat with you and remember previous sessions thanks to the chat history.
- Streamed responses.
- 

## Roadmap
- Complete RAG and Knowledge Graph, they will activate "manually" (not for you) so they won't always research through your stuff each time you send a text. [80% completed]
- TTS + Vocal transcription [0% Completed]
- Markdown editor (Obsidian Style) with Merlin inline, every once in a while, Merlin will check what you wrote and help you fix errors, or even suggest similar or strictly correlated topics you might find useful from your chat history and his RAG/KG! [0% Completed]
- Plugin System for intent -> local action. You could write any script you'd like, for example, a script that will create folders and files for a new Python project, and you'll only have to say "Hey Merlin, can you create a new project in [folder] with git enabled, please?" [0% completed]
- Multi-Chat system with cross-session RAG

## Stack
Python, FastAPI, LlamaIndex, Ollama, SQLite, JS/HTML/CSS

## Run Locally
If you want to try it in this early stage, you can do so with these steps:
### Requirements
- Python 3.14.3+
- [Ollama](https://ollama.com/) installed and running
- Any model you'd want to be installed:
You'll want at least two: `ollama pull nomic-embed-text` and any LLM you like, though, the goal for this tool is to be usable with very small LLM's too! I use `qwen3.5:9b` but the goal is to be usable with even smaller ones.
### Setup
```bash
git clone https://github.com/SaruboDev/Merlin
cd Merlin
pip install -r requirements.txt
python main.py
```

Then the console will give you the local address to use in your browser!

## Contributing
Found a bug or have a feature idea? Open an issue!
