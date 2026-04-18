import os
from typing import Any

from torch._numpy import True_
os.environ['TRANSFORMERS_OFFLINE'] = "1"
os.environ['HF_HUB_OFFLINE'] = "1"

import numpy as np
import spacy
from spacy.matcher import PhraseMatcher

import pathlib
from pathlib import Path
import importlib.util

import time

import json

from tools import write_event

from sentence_transformers import SentenceTransformer, util
from typing import Any

"""
Questo script prende le query dell'utente estrae le info necessarie per trovare ed eseguire plugin/script.
"""

def extract_keywords(manifest: Path):
    """
    This function extracts the keywords from each manifest.json in the plugins folder.
    """
    with open(manifest, "r") as plugin:
        file = json.load(plugin)
        keywords = []
        if not isinstance(file["keywords"], list):
            keywords = list(file["keywords"])
        else:
            keywords = file["keywords"]
        if not isinstance(file["intent_keywords"], dict):
            raise Exception("Can't use non dict for intent keywords parameter. Use dict[str, list[str]] as structure.")
        intent_keywords = file["intent_keywords"]
        return keywords, intent_keywords

def search_plugins(model: SentenceTransformer) -> dict:
    """
    This function searches all plugins that have the manifest.json file inside them.
    """
    os.chdir("..")

    found_plugins: dict = {}

    for root, dirs, files in os.walk("plugins/"):
        if "manifest.json" in files:
            plugin_path = Path(root)
            plugin_name: str = root.strip("plugins/")

            keywords, intent_keywords = extract_keywords(plugin_path / "manifest.json")
            found_plugins[plugin_name] = {
                "executable": plugin_path / "main.py",
                "keywords": model.encode(keywords, convert_to_numpy = True, normalize_embeddings = True),
                "intent_keywords": intent_keywords
            }

    write_event("Search Plugin: Done.")

    return found_plugins

def load_cpu_embedder() -> SentenceTransformer:
    """
    Loads the cpu embedding model.
    """
    model: SentenceTransformer = SentenceTransformer(
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        device = "cpu")
    return model

def load_language_model():
    """
    Searches and downloads/loads the language model
    """
    # lang_map = {
    #     "en": "en_core_web_sm",
    #     "it": "it_core_news_sm"
    # }
    try:
        language_model = spacy.load("en_core_web_sm")
    except IOError:
        # If spacy doesn't find the model already installed, we download it.
        spacy.cli.download("en_core_web_sm")
        language_model = spacy.load("en_core_web_sm")
    return language_model

model = load_cpu_embedder()
plugins = search_plugins(model)
language_model = load_language_model()

def run_plugin(path: Path): # NGL i couldn't find anything about this so i asked gpt
    """
    NOTE: Gotta search for another way because i also gotta give which intent got extracted.
    """
    try:
        spec = importlib.util.spec_from_file_location("plugin", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        write_event("Ran Plugin successfully.")

        return {"ran plugin": True}
    except Exception as e:
        write_event(f"Run Plugin Error: {e}")
        return {"ran plugin": False}

def extract_intent(query: str, plugin_exec, intent_keywords):
    """
    This function extracts the intent from the user's query using the plugin's manifest data.
    """

    matcher = PhraseMatcher(language_model.vocab, attr = "LOWER")

    for intent, keywords in intent_keywords.items():
        patterns = [language_model(text) for text in keywords]
        matcher.add(intent, patterns)

    doc = language_model(query)
    matches = matcher(doc)
    for match_id, start, end in matches:
        intent_name = language_model.vocab.strings[match_id]
        run_plugin(plugin_exec)

def should_run_plugin(query: str, plugins: dict, model: SentenceTransformer):
    query_embed = model.encode(query, convert_to_numpy = True, normalize_embeddings = True)

    plugin_distances = {}
    for name, plugin in zip(plugins.keys(), plugins.values()):

        similarity_cos = util.cos_sim(plugin["keywords"], query_embed).tolist()
        similarity_cos = [i[0] for i in similarity_cos]

        plugin_distances[name] = np.max(similarity_cos)

    max_plugin = max(plugin_distances)
    max_plugin_value = plugin_distances[max_plugin]
    if max_plugin_value >= 0.6:
        extract_intent(query, plugin["executable"], plugin["intent_keywords"])


superman = 23 # i want to print the variable superman
should_run_plugin("i want to print the variable superman", plugins, model)
# def find_something_local(query: str):
#     s = time.time()

#     embedding = model.encode(query, convert_to_numpy=True)

#     print(f"Time CPU: {(time.time() - s):.4f} seconds")
#     return embedding

# embed = find_something_local("We should test this")

# embed2 = model.encode("Can you test this?")

# print("Similarity: ", util.cos_sim(embed, embed2).item())
