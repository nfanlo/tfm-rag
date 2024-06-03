class BaseLogger:
    def __init__(self) -> None:
        self.info = print

def extract_title_and_question(input_string):
    lines = input_string.strip().split("\n")

    title = ""
    question = ""
    is_question = False

    for line in lines:
        if line.startswith("Title:"):
            title = line.split("Title: ", 1)[1].strip()
        elif line.startswith("Question:"):
            question = line.split("Question: ", 1)[1].strip()
            is_question = (True)
        elif is_question:
            question += "\n" + line.strip()

    return title, question