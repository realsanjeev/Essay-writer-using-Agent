from src.agent import Agent
from src.writer_gui import WriterGUI

if __name__ == "__main__":
    MultiAgent = Agent()
    app = WriterGUI(MultiAgent.graph)
    app.launch()
