import datetime
from pathlib import Path

###############
### Logging ###
###############

ROOT_DIR = Path(__file__).resolve().parent.parent
def write_event(event: str, start_new: bool = False, print_console: bool = True) -> None:
    """
    Simply writes the current event to the log.txt file.
    """
    current_time = datetime.datetime.now()
    match start_new:
        case True:
            with open(ROOT_DIR / "log.txt", "w") as log:
                log.write(str(current_time) + " " + event + "\n")
        case False:
            with open(ROOT_DIR/ "log.txt", "a") as log:
                log.write(str(current_time) + " " + event + "\n")

    if print_console:
        print(str(current_time) + " " + event)
