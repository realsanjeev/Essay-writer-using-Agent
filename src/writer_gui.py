import os

import gradio as gr


class WriterGUI:
    def __init__(self, graph, share=False):
        self.graph = graph
        self.share = share
        self.partial_message = ""
        self.response = {}
        self.max_iterations = 10
        self.iterations = []
        self.threads = []
        self.thread_id = -1
        self.thread = {"configurable": {"thread_id": str(self.thread_id)}}
        # self.sdisps = {} #global
        self.demo = self.create_interface()

    def run_agent(self, start, topic, stop_after):
        # global partial_message, thread_id,thread
        # global response, max_iterations, iterations, threads
        if start:
            self.iterations.append(0)
            config = {
                "task": topic,
                "max_revisions": 2,
                "revision_number": 0,
                "lnode": "",
                "planner": "no plan",
                "draft": "no draft",
                "critique": "no critique",
                "content": [
                    "no content",
                ],
                "queries": "no queries",
                "count": 0,
            }
            self.thread_id += 1  # new agent, new thread
            self.threads.append(self.thread_id)
        else:
            config = None
        self.thread = {"configurable": {"thread_id": str(self.thread_id)}}
        while self.iterations[self.thread_id] < self.max_iterations:
            self.response = self.graph.invoke(config, self.thread)
            self.iterations[self.thread_id] += 1
            self.partial_message += str(self.response)
            self.partial_message += "\n------------------\n\n"
            ## fix
            lnode, nnode, _, rev, acount = self.get_disp_state()
            yield self.partial_message, lnode, nnode, self.thread_id, rev, acount
            config = None  # need
            # print(f"run_agent:{lnode}")
            if not nnode:
                # print("Hit the end")
                return
            if lnode in stop_after:
                # print(f"stopping due to stop_after {lnode}")
                return
            else:
                # print(f"Not stopping on lnode {lnode}")
                pass
        return

    def get_disp_state(
        self,
    ):
        current_state = self.graph.get_state(self.thread)
        lnode = current_state.values["lnode"]
        acount = current_state.values["count"]
        rev = current_state.values["revision_number"]
        nnode = current_state.next
        # print  (lnode,nnode,self.thread_id,rev,acount)
        return lnode, nnode, self.thread_id, rev, acount

    def get_state(self, key):
        current_values = self.graph.get_state(self.thread)
        if key in current_values.values:
            lnode, nnode, self.thread_id, rev, astep = self.get_disp_state()
            new_label = f"last_node: {lnode}, thread_id: {self.thread_id}, rev: {rev}, step: {astep}"
            return gr.update(label=new_label, value=current_values.values[key])
        else:
            return ""

    def get_content(
        self,
    ):
        current_values = self.graph.get_state(self.thread)
        if "content" in current_values.values:
            content = current_values.values["content"]
            lnode, nnode, thread_id, rev, astep = self.get_disp_state()
            new_label = f"last_node: {lnode}, thread_id: {self.thread_id}, rev: {rev}, step: {astep}"
            return gr.update(
                label=new_label, value="\n\n".join(item for item in content) + "\n\n"
            )
        else:
            return ""

    def update_hist_pd(
        self,
    ):
        # print("update_hist_pd")
        hist = []
        # curiously, this generator returns the latest first
        for state in self.graph.get_state_history(self.thread):
            if state.metadata["step"] < 1:
                continue
            thread_ts = state.config["configurable"]["thread_ts"]
            tid = state.config["configurable"]["thread_id"]
            count = state.values["count"]
            lnode = state.values["lnode"]
            rev = state.values["revision_number"]
            nnode = state.next
            st = f"{tid}:{count}:{lnode}:{nnode}:{rev}:{thread_ts}"
            hist.append(st)
        return gr.Dropdown(
            label="update_state from: thread:count:last_node:next_node:rev:thread_ts",
            choices=hist,
            value=hist[0],
            interactive=True,
        )

    def find_config(self, thread_ts):
        for state in self.graph.get_state_history(self.thread):
            config = state.config
            if config["configurable"]["thread_ts"] == thread_ts:
                return config
        return None

    def copy_state(self, hist_str):
        """result of selecting an old state from the step pulldown. Note does not change thread.
        This copies an old state to a new current state.
        """
        thread_ts = hist_str.split(":")[-1]
        # print(f"copy_state from {thread_ts}")
        config = self.find_config(thread_ts)
        # print(config)
        state = self.graph.get_state(config)
        self.graph.update_state(
            self.thread, state.values, as_node=state.values["lnode"]
        )
        new_state = self.graph.get_state(self.thread)  # should now match
        new_thread_ts = new_state.config["configurable"]["thread_ts"]
        new_state.config["configurable"]["thread_id"]
        count = new_state.values["count"]
        lnode = new_state.values["lnode"]
        rev = new_state.values["revision_number"]
        nnode = new_state.next
        return lnode, nnode, new_thread_ts, rev, count

    def update_thread_pd(
        self,
    ):
        # print("update_thread_pd")
        return gr.Dropdown(
            label="choose thread",
            choices=self.threads,
            value=self.thread_id,
            interactive=True,
        )

    def switch_thread(self, new_thread_id):
        # print(f"switch_thread{new_thread_id}")
        self.thread = {"configurable": {"thread_id": str(new_thread_id)}}
        self.thread_id = new_thread_id
        return

    def modify_state(self, key, asnode, new_state):
        """
        Modifies a single value identified by 'key' in the current state, updates the state with the new value.

        This method retrieves the current state from the graph, updates the specified value identified by 'key'
        with 'new_state', and then updates the state in the graph. Note that this operation creates a new 'current state'
        node each time it is called with different keys, as identified by 'asnode'.

        Parameters:
        - key (str): The key identifying the value to modify in the state.
        - asnode (str): Identifier for the node to update in the graph after modification.
        - new_state (any): The new value to assign to the specified key in the state.

        Note:
        - Calling this method multiple times with different keys will create a new 'current state' node for each update.
        - After modification, the method does not resume execution in the updated state.
        """
        current_values = self.graph.get_state(self.thread)
        current_values.values[key] = new_state
        self.graph.update_state(self.thread, current_values.values, as_node=asnode)
        return

    def create_interface(self):
        with gr.Blocks(
            theme=gr.themes.Default(spacing_size="sm", text_size="sm")
        ) as demo:

            def updt_disp():
                """general update display on state change"""
                current_state = self.graph.get_state(self.thread)
                hist = []
                # curiously, this generator returns the latest first
                for state in self.graph.get_state_history(self.thread):
                    if state.metadata["step"] < 1:  # ignore early states
                        continue
                    s_thread_ts = state.config["configurable"]["thread_ts"]
                    s_tid = state.config["configurable"]["thread_id"]
                    s_count = state.values["count"]
                    s_lnode = state.values["lnode"]
                    s_rev = state.values["revision_number"]
                    s_nnode = state.next
                    st = f"{s_tid}:{s_count}:{s_lnode}:{s_nnode}:{s_rev}:{s_thread_ts}"
                    hist.append(st)
                if not current_state.metadata:  # handle init call
                    return {}
                else:
                    return {
                        topic_bx: current_state.values["task"],
                        lnode_bx: current_state.values["lnode"],
                        count_bx: current_state.values["count"],
                        revision_bx: current_state.values["revision_number"],
                        nnode_bx: current_state.next,
                        threadid_bx: self.thread_id,
                        thread_pd: gr.Dropdown(
                            label="choose thread",
                            choices=self.threads,
                            value=self.thread_id,
                            interactive=True,
                        ),
                        step_pd: gr.Dropdown(
                            label="update_state from: thread:count:last_node:next_node:rev:thread_ts",
                            choices=hist,
                            value=hist[0],
                            interactive=True,
                        ),
                    }

            def get_snapshots():
                new_label = f"thread_id: {self.thread_id}, Summary of snapshots"
                sstate = ""
                for state in self.graph.get_state_history(self.thread):
                    for key in ["plan", "draft", "critique"]:
                        if key in state.values:
                            state.values[key] = state.values[key][:80] + "..."
                    if "content" in state.values:
                        for i in range(len(state.values["content"])):
                            state.values["content"][i] = (
                                state.values["content"][i][:20] + "..."
                            )
                    if "writes" in state.metadata:
                        state.metadata["writes"] = "not shown"
                    sstate += str(state) + "\n\n"
                return gr.update(label=new_label, value=sstate)

            def vary_btn(stat):
                # print(f"vary_btn{stat}")
                return gr.update(variant=stat)

            with gr.Tab("Agent"):
                with gr.Row():
                    topic_bx = gr.Textbox(
                        label="Essay Topic", value="TAI Inc in Nepal and its CEO"
                    )
                    gen_btn = gr.Button(
                        "Generate Essay", scale=0, min_width=80, variant="primary"
                    )
                    cont_btn = gr.Button("Continue Essay", scale=0, min_width=80)
                with gr.Row():
                    lnode_bx = gr.Textbox(label="last node", min_width=100)
                    nnode_bx = gr.Textbox(label="next node", min_width=100)
                    threadid_bx = gr.Textbox(label="Thread", scale=0, min_width=80)
                    revision_bx = gr.Textbox(label="Draft Rev", scale=0, min_width=80)
                    count_bx = gr.Textbox(label="count", scale=0, min_width=80)
                with gr.Accordion("Manage Agent", open=False):
                    checks = list(self.graph.nodes.keys())
                    checks.remove("__start__")
                    stop_after = gr.CheckboxGroup(
                        checks,
                        label="Interrupt After State",
                        value=checks,
                        scale=0,
                        min_width=400,
                    )
                    with gr.Row():
                        thread_pd = gr.Dropdown(
                            choices=self.threads,
                            interactive=True,
                            label="select thread",
                            min_width=120,
                            scale=0,
                        )
                        step_pd = gr.Dropdown(
                            choices=["N/A"],
                            interactive=True,
                            label="select step",
                            min_width=160,
                            scale=1,
                        )
                live = gr.Textbox(label="Live Agent Output", lines=5, max_lines=5)

                # actions
                sdisps = [
                    topic_bx,
                    lnode_bx,
                    nnode_bx,
                    threadid_bx,
                    revision_bx,
                    count_bx,
                    step_pd,
                    thread_pd,
                ]
                thread_pd.input(self.switch_thread, [thread_pd], None).then(
                    fn=updt_disp, inputs=None, outputs=sdisps
                )
                step_pd.input(self.copy_state, [step_pd], None).then(
                    fn=updt_disp, inputs=None, outputs=sdisps
                )
                gen_btn.click(
                    vary_btn, gr.Number("secondary", visible=False), gen_btn
                ).then(
                    fn=self.run_agent,
                    inputs=[gr.Number(True, visible=False), topic_bx, stop_after],
                    outputs=[live],
                    show_progress=True,
                ).then(
                    fn=updt_disp, inputs=None, outputs=sdisps
                ).then(
                    vary_btn, gr.Number("primary", visible=False), gen_btn
                ).then(
                    vary_btn, gr.Number("primary", visible=False), cont_btn
                )
                cont_btn.click(
                    vary_btn, gr.Number("secondary", visible=False), cont_btn
                ).then(
                    fn=self.run_agent,
                    inputs=[gr.Number(False, visible=False), topic_bx, stop_after],
                    outputs=[live],
                ).then(
                    fn=updt_disp, inputs=None, outputs=sdisps
                ).then(
                    vary_btn, gr.Number("primary", visible=False), cont_btn
                )

            with gr.Tab("Plan"):
                with gr.Row():
                    refresh_btn = gr.Button("Refresh")
                    modify_btn = gr.Button("Modify")
                plan = gr.Textbox(label="Plan", lines=10, interactive=True)
                refresh_btn.click(
                    fn=self.get_state,
                    inputs=gr.Number("plan", visible=False),
                    outputs=plan,
                )
                modify_btn.click(
                    fn=self.modify_state,
                    inputs=[
                        gr.Number("plan", visible=False),
                        gr.Number("planner", visible=False),
                        plan,
                    ],
                    outputs=None,
                ).then(fn=updt_disp, inputs=None, outputs=sdisps)
            with gr.Tab("Research Content"):
                refresh_btn = gr.Button("Refresh")
                content_bx = gr.Textbox(label="content", lines=10)
                refresh_btn.click(fn=self.get_content, inputs=None, outputs=content_bx)
            with gr.Tab("Draft"):
                with gr.Row():
                    refresh_btn = gr.Button("Refresh")
                    modify_btn = gr.Button("Modify")
                draft_bx = gr.Textbox(label="draft", lines=10, interactive=True)
                refresh_btn.click(
                    fn=self.get_state,
                    inputs=gr.Number("draft", visible=False),
                    outputs=draft_bx,
                )
                modify_btn.click(
                    fn=self.modify_state,
                    inputs=[
                        gr.Number("draft", visible=False),
                        gr.Number("generate", visible=False),
                        draft_bx,
                    ],
                    outputs=None,
                ).then(fn=updt_disp, inputs=None, outputs=sdisps)
            with gr.Tab("Critique"):
                with gr.Row():
                    refresh_btn = gr.Button("Refresh")
                    modify_btn = gr.Button("Modify")
                critique_bx = gr.Textbox(label="Critique", lines=10, interactive=True)
                refresh_btn.click(
                    fn=self.get_state,
                    inputs=gr.Number("critique", visible=False),
                    outputs=critique_bx,
                )
                modify_btn.click(
                    fn=self.modify_state,
                    inputs=[
                        gr.Number("critique", visible=False),
                        gr.Number("reflect", visible=False),
                        critique_bx,
                    ],
                    outputs=None,
                ).then(fn=updt_disp, inputs=None, outputs=sdisps)
            with gr.Tab("StateSnapShots"):
                with gr.Row():
                    refresh_btn = gr.Button("Refresh")
                snapshots = gr.Textbox(label="State Snapshots Summaries")
                refresh_btn.click(fn=get_snapshots, inputs=None, outputs=snapshots)
        return demo

    def launch(self, share=None):
        if port := os.getenv("PORT1"):
            self.demo.launch(share=True, server_port=int(port), server_name="0.0.0.0")
        else:
            self.demo.launch(share=self.share)
