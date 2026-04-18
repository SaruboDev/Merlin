import toml
from pathlib import Path

ROOT_DIR: Path = Path(__file__).resolve().parent.parent

def load_settings() -> dict[str, Any]:
    """
    Loads the settings from file.
    """
    base_opt: dict[str, Any] = {
        "Model" : {
            "name"      : "qwen3.5:9b",
            "reasoning" : "False",
            "streaming" : "True"
        } ,
        "Global": {
            "max_history": 10,
            "language": "it",
        }
    }
    options_path: Path = ROOT_DIR / Path("settings.toml")
    if not options_path.exists():
        with open(options_path, "w") as file:
            toml.dump(base_opt, file)

    with open(ROOT_DIR / "settings.toml", "r") as f:
        options: dict[str, Any] = toml.load(f)

    settings: dict[str, Any] = {
        "Model": {
            "model_name": options["Model"]["name"],
            "reasoning" : options["Model"]["reasoning"],
            "streaming" : options["Model"]["streaming"]
        },
        "Global": {
            "max_history": int(options["Global"]["max_history"]),
            "language": options["Global"]["language"]
        }
    }
    return settings

def save_settings(settings) -> None:
    """
    Saves the current settings to file.
    """
    new_opt: dict[str, Any] = {
        "Model" : {
            "name" : settings["Model"]["model_name"],
            "reasoning" : settings["Model"]["reasoning"],
            "streaming" : settings["Model"]["streaming"]
        },
        "Global": {
            "max_history": int(settings["Global"]["max_history"]),
            "language": settings["Global"]["language"]
        }
    }

    options_path: Path = ROOT_DIR / Path("settings.toml")
    with open(options_path, "w") as file:
        toml.dump(new_opt, file)
