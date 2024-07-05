from dotenv import load_dotenv

from src.agent import Agent
from src.writer_gui import WriterGUI

if __name__ == "__main__":
    _ = load_dotenv()
    MultiAgent = Agent()
    app = WriterGUI(MultiAgent.graph)
    app.launch()
