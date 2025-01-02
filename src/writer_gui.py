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
            checkpoint_id = state.config["configurable"]["checkpoint_id"]
            tid = state.config["configurable"]["thread_id"]
            count = state.values["count"]
            lnode = state.values["lnode"]
            rev = state.values["revision_number"]
            nnode = state.next
            st = f"{tid}:{count}:{lnode}:{nnode}:{rev}:{checkpoint_id}"
            hist.append(st)
        return gr.Dropdown(
            label="update_state from: thread:count:last_node:next_node:rev:checkpoint_id",
            choices=hist,
            value=hist[0],
            interactive=True,
        )

    def find_config(self, checkpoint_id):
        for state in self.graph.get_state_history(self.thread):
            config = state.config
            if config["configurable"]["checkpoint_id"] == checkpoint_id:
                return config
        return None

    def copy_state(self, hist_str):
        """result of selecting an old state from the step pulldown. Note does not change thread.
        This copies an old state to a new current state.
        """
        if not hist_str:
            return None, None, None, None, None

        checkpoint_id = hist_str.split(":")[-1]
        # print(f"copy_state from {checkpoint_id}")
        config = self.find_config(checkpoint_id)

        # Handle case where config is not found
        if config is None:
            print(f"Warning: Could not find config for checkpoint {checkpoint_id}")
            return None, None, None, None, None

        # print(config)
        state = self.graph.get_state(config)
        self.graph.update_state(
            self.thread, state.values, as_node=state.values["lnode"]
        )
        new_state = self.graph.get_state(self.thread)  # should now match
        new_checkpoint_id = new_state.config["configurable"]["checkpoint_id"]
        new_state.config["configurable"]["thread_id"]
        count = new_state.values["count"]
        lnode = new_state.values["lnode"]
        rev = new_state.values["revision_number"]
        nnode = new_state.next
        return lnode, nnode, new_checkpoint_id, rev, count

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
        # Custom CSS for better styling
        custom_css = """
        .gradio-container {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif !important;
        }
        .main-header {
            text-align: center;
            padding: 1.5rem 0;
            background: linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%);
            color: white;
            border-radius: 8px;
            margin-bottom: 1.5rem;
        }
        .status-box {
            border-left: 3px solid #3b82f6;
            padding-left: 0.5rem;
        }
        .primary-btn {
            background: linear-gradient(135deg, #3b82f6 0%, #06b6d4 100%) !important;
            border: none !important;
            color: white !important;
            font-weight: 600 !important;
            transition: transform 0.2s !important;
        }
        .primary-btn:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(59, 130, 246, 0.4) !important;
        }
        .tab-nav button {
            font-weight: 500 !important;
            padding: 0.75rem 1.5rem !important;
        }
        .output-box {
            border: 1px solid #e5e7eb;
            border-radius: 8px;
            background: #f9fafb;
        }
        textarea {
            font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace !important;
            line-height: 1.6 !important;
        }
        .refresh-btn {
            background: #10b981 !important;
            color: white !important;
        }
        .modify-btn {
            background: #f59e0b !important;
            color: white !important;
        }
        </style>
        """

        with gr.Blocks(
            theme=gr.themes.Soft(
                primary_hue="blue",
                secondary_hue="cyan",
                neutral_hue="slate",
                spacing_size="md",
                text_size="md",
            ),
            css=custom_css,
            title="Quality Essay Writer",
        ) as demo:

            def updt_disp():
                """general update display on state change"""
                current_state = self.graph.get_state(self.thread)
                hist = []
                # curiously, this generator returns the latest first
                for state in self.graph.get_state_history(self.thread):
                    if state.metadata.get("step", 0) < 1:  # ignore early states
                        continue
                    print(state.config["configurable"])
                    s_checkpoint_id = state.config["configurable"]["checkpoint_id"]
                    s_tid = state.config["configurable"]["thread_id"]
                    s_count = state.values["count"]
                    s_lnode = state.values["lnode"]
                    s_rev = state.values["revision_number"]
                    s_nnode = state.next
                    st = f"{s_tid}:{s_count}:{s_lnode}:{s_nnode}:{s_rev}:{s_checkpoint_id}"
                    hist.append(st)

                # Handle init call - return proper None values for all 8 outputs
                if not current_state.metadata:
                    return None, None, None, None, None, None, None, None

                # Return proper updates for all components
                return {
                    topic_bx: current_state.values.get("task", ""),
                    lnode_bx: current_state.values.get("lnode", ""),
                    count_bx: current_state.values.get("count", ""),
                    revision_bx: current_state.values.get("revision_number", ""),
                    nnode_bx: current_state.next if current_state.next else "",
                    threadid_bx: self.thread_id,
                    thread_pd: gr.Dropdown(
                        label="choose thread",
                        choices=self.threads,
                        value=self.thread_id,
                        interactive=True,
                    ),
                    step_pd: gr.Dropdown(
                        label="update_state from: thread:count:last_node:next_node:rev:checkpoint_id",
                        choices=hist if hist else ["N/A"],
                        value=hist[0] if hist else "N/A",
                        interactive=True,
                    ),
                }

            def get_snapshots():
                """Format state snapshots in a nice, readable format"""
                new_label = f"📸 Thread {self.thread_id} - State History"
                sstate = ""

                snapshot_count = 0
                for state in self.graph.get_state_history(self.thread):
                    if state.metadata.get("step", 0) < 1:
                        continue

                    snapshot_count += 1
                    checkpoint_id = state.config["configurable"]["checkpoint_id"]

                    # Header for each snapshot
                    sstate += "=" * 80 + "\n"
                    sstate += f"📌 SNAPSHOT #{snapshot_count}\n"
                    sstate += "=" * 80 + "\n\n"

                    # Basic info
                    sstate += f"🔹 Checkpoint ID: {checkpoint_id[:16]}...\n"
                    sstate += (
                        f"🔹 Thread ID: {state.config['configurable']['thread_id']}\n"
                    )
                    sstate += f"🔹 Step: {state.values.get('count', 'N/A')}\n"
                    sstate += f"🔹 Last Node: {state.values.get('lnode', 'N/A')}\n"
                    sstate += f"🔹 Next Node: {state.next if state.next else 'END'}\n"
                    sstate += (
                        f"🔹 Revision: {state.values.get('revision_number', 'N/A')}\n"
                    )
                    sstate += "\n"

                    # Task
                    if "task" in state.values:
                        sstate += f"📝 Task:\n   {state.values['task']}\n\n"

                    # Plan preview
                    if "plan" in state.values and state.values["plan"] != "no plan":
                        plan_preview = state.values["plan"][:150].replace("\n", " ")
                        sstate += f"📋 Plan Preview:\n   {plan_preview}...\n\n"

                    # Draft preview
                    if "draft" in state.values and state.values["draft"] != "no draft":
                        draft_preview = state.values["draft"][:150].replace("\n", " ")
                        sstate += f"✍️ Draft Preview:\n   {draft_preview}...\n\n"

                    # Critique preview
                    if (
                        "critique" in state.values
                        and state.values["critique"] != "no critique"
                    ):
                        critique_preview = state.values["critique"][:150].replace(
                            "\n", " "
                        )
                        sstate += f"💭 Critique Preview:\n   {critique_preview}...\n\n"

                    # Content count
                    if "content" in state.values and state.values["content"] != [
                        "no content"
                    ]:
                        content_count = len(state.values["content"])
                        sstate += f"🔍 Research Items: {content_count}\n"
                        for i, item in enumerate(state.values["content"][:3], 1):
                            preview = item[:100].replace("\n", " ")
                            sstate += f"   {i}. {preview}...\n"
                        if content_count > 3:
                            sstate += f"   ... and {content_count - 3} more items\n"
                        sstate += "\n"

                    # Queries
                    if (
                        "queries" in state.values
                        and state.values["queries"] != "no queries"
                    ):
                        sstate += f"🔎 Queries: {state.values['queries']}\n\n"

                    sstate += "\n"

                if snapshot_count == 0:
                    sstate = "No snapshots available yet. Run the agent to generate snapshots."

                return gr.update(label=new_label, value=sstate)

            def vary_btn(stat):
                # print(f"vary_btn{stat}")
                return gr.update(variant=stat)

            # Add header
            gr.Markdown(
                """<div class='main-header'>
                <h1>📝 Quality Essay Writer</h1>
                <p>AI-powered essay generation with multi-agent workflow</p>
                </div>"""
            )

            with gr.Tab("Agent"):
                with gr.Row():
                    topic_bx = gr.Textbox(
                        label="📚 Essay Topic",
                        placeholder="Enter your essay topic here...",
                        value="TAI Inc in Nepal and its CEO",
                        lines=2,
                        scale=3,
                    )
                with gr.Row():
                    gen_btn = gr.Button(
                        "🚀 Generate Essay",
                        scale=1,
                        variant="primary",
                        size="lg",
                    )
                    cont_btn = gr.Button(
                        "▶️ Continue Essay",
                        scale=1,
                        variant="secondary",
                        size="lg",
                    )

                gr.Markdown("### 📊 Agent Status")
                with gr.Row():
                    lnode_bx = gr.Textbox(
                        label="🔵 Last Node",
                        interactive=False,
                        scale=1,
                    )
                    nnode_bx = gr.Textbox(
                        label="🟢 Next Node",
                        interactive=False,
                        scale=1,
                    )
                with gr.Row():
                    threadid_bx = gr.Textbox(
                        label="🧵 Thread ID",
                        interactive=False,
                        scale=1,
                    )
                    revision_bx = gr.Textbox(
                        label="📝 Draft Revision",
                        interactive=False,
                        scale=1,
                    )
                    count_bx = gr.Textbox(
                        label="🔢 Step Count",
                        interactive=False,
                        scale=1,
                    )
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
                gr.Markdown("### 📡 Live Agent Output")
                live = gr.Textbox(
                    label="",
                    lines=12,
                    max_lines=20,
                    show_label=False,
                    container=True,
                    elem_classes=["output-box"],
                )

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

            with gr.Tab("📋 Plan") as plan_tab:
                gr.Markdown("### Essay Planning")
                with gr.Row():
                    refresh_btn = gr.Button(
                        "🔄 Refresh",
                        variant="primary",
                        elem_classes=["refresh-btn"],
                    )
                    modify_btn = gr.Button(
                        "✏️ Modify Plan",
                        variant="secondary",
                        elem_classes=["modify-btn"],
                    )
                plan = gr.Textbox(
                    label="Plan Content",
                    lines=15,
                    max_lines=25,
                    interactive=True,
                    placeholder="Essay plan will appear here...",
                )
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
            with gr.Tab("🔍 Research Content") as research_tab:
                gr.Markdown("### Research Materials")
                refresh_btn = gr.Button(
                    "🔄 Refresh Content",
                    variant="primary",
                    elem_classes=["refresh-btn"],
                )
                content_bx = gr.Textbox(
                    label="Research Content",
                    lines=15,
                    max_lines=25,
                    placeholder="Research content will appear here...",
                )
                refresh_btn.click(fn=self.get_content, inputs=None, outputs=content_bx)
            with gr.Tab("✍️ Draft"):
                gr.Markdown("### Essay Draft")
                with gr.Row():
                    refresh_btn = gr.Button(
                        "🔄 Refresh",
                        variant="primary",
                        elem_classes=["refresh-btn"],
                    )
                    modify_btn = gr.Button(
                        "✏️ Modify Draft",
                        variant="secondary",
                        elem_classes=["modify-btn"],
                    )
                draft_bx = gr.Textbox(
                    label="Draft Content",
                    lines=15,
                    max_lines=25,
                    interactive=True,
                    placeholder="Essay draft will appear here...",
                )
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
            with gr.Tab("💭 Critique"):
                gr.Markdown("### Essay Critique & Feedback")
                with gr.Row():
                    refresh_btn = gr.Button(
                        "🔄 Refresh",
                        variant="primary",
                        elem_classes=["refresh-btn"],
                    )
                    modify_btn = gr.Button(
                        "✏️ Modify Critique",
                        variant="secondary",
                        elem_classes=["modify-btn"],
                    )
                critique_bx = gr.Textbox(
                    label="Critique Content",
                    lines=15,
                    max_lines=25,
                    interactive=True,
                    placeholder="Essay critique will appear here...",
                )
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
            with gr.Tab("📸 State Snapshots"):
                gr.Markdown("### Agent State History")
                refresh_btn = gr.Button(
                    "🔄 Refresh Snapshots",
                    variant="primary",
                    elem_classes=["refresh-btn"],
                )
                snapshots = gr.Textbox(
                    label="State Snapshots Summaries",
                    lines=15,
                    max_lines=25,
                    placeholder="State snapshots will appear here...",
                )
                refresh_btn.click(fn=get_snapshots, inputs=None, outputs=snapshots)

            # Auto-refresh when navigating to Plan and Research tabs
            plan_tab.select(
                fn=self.get_state,
                inputs=gr.Number("plan", visible=False),
                outputs=plan,
            )
            research_tab.select(
                fn=self.get_content,
                inputs=None,
                outputs=content_bx,
            )

        return demo

    def launch(self, share=None):
        if port := os.getenv("PORT1"):
            self.demo.launch(share=True, server_port=int(port), server_name="0.0.0.0")
        else:
            self.demo.launch(share=self.share)
