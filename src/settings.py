import toml
from pathlib import Path

def load_settings():
    """
    Loads the settings from file.
    """
    base_opt = {
        "Model" : {
            "name"      : "qwen3.5:9b",
            "reasoning" : "False",
            "streaming" : "True"
        } ,
        "Global": {
            "max_history": 10,
        }
    }
    options_path = Path("settings.toml")
    if not options_path.exists():
        with open(options_path, "w") as file:
            toml.dump(base_opt, file)

    with open("settings.toml", "r") as f:
        options = toml.load(f)

    settings = {
        "Model": {
            "model_name": options["Model"]["name"],
            "reasoning" : options["Model"]["reasoning"],
            "streaming" : options["Model"]["streaming"]
        },
        "Global": {
            "max_history": int(options["Global"]["max_history"])
        }
    }
    return settings

def save_settings(settings):
    """
    Saves the current settings to file.
    """
    new_opt = {
        "Model" : {
            "name" : settings["Model"]["model_name"],
            "reasoning" : settings["Model"]["reasoning"],
            "streaming" : settings["Model"]["streaming"]
        },
        "Global": {
            "max_history": int(settings["Global"]["max_history"])
        }
    }

    options_path = Path("settings.toml")
    with open(options_path, "w") as file:
        toml.dump(new_opt, file)