"""
Chatbot Arena (side-by-side) tab.
Users chat with two chosen models.
"""

import json
import time

import gradio as gr
from gradio_sandboxcomponent import SandboxComponent
import numpy as np

from fastchat.constants import (
    MODERATION_MSG,
    CONVERSATION_LIMIT_MSG,
    INPUT_CHAR_LEN_LIMIT,
    CONVERSATION_TURN_LIMIT,
    SURVEY_LINK,
)
from fastchat.model.model_adapter import get_conversation_template
from fastchat.serve.gradio_web_server import (
    State,
    add_text,
    bot_response,
    get_conv_log_filename,
    no_change_btn,
    enable_btn,
    disable_btn,
    invisible_btn,
    acknowledgment_md,
    get_ip,
    get_model_description_md,
    update_sandbox_system_message
)
from fastchat.serve.remote_logger import get_remote_logger
from fastchat.serve.sandbox.code_runner import SandboxGradioSandboxComponents, SandboxEnvironment, DEFAULT_SANDBOX_INSTRUCTIONS, SUPPORTED_SANDBOX_ENVIRONMENTS, ChatbotSandboxState, create_chatbot_sandbox_state, on_click_code_message_run, on_edit_code, update_sandbox_config_multi, update_visibility
from fastchat.utils import (
    build_logger,
    moderation_filter,
)

logger = build_logger("gradio_web_server_multi", "gradio_web_server_multi.log")

num_sides = 2
enable_moderation = False


def set_global_vars_named(enable_moderation_):
    global enable_moderation
    enable_moderation = enable_moderation_


def load_demo_side_by_side_named(models, url_params):
    states = [None] * num_sides

    model_left = models[0] if len(models) > 0 else ""
    if len(models) > 1:
        weights = ([8] * 4 + [4] * 8 + [1] * 64)[: len(models) - 1]
        weights = weights / np.sum(weights)
        model_right = np.random.choice(models[1:], p=weights)
    else:
        model_right = model_left

    selector_updates = [
        gr.Dropdown(choices=models, value=model_left, visible=True),
        gr.Dropdown(choices=models, value=model_right, visible=True),
    ]

    return states + selector_updates


def vote_last_response(states, vote_type, model_selectors, request: gr.Request):
    if states[0] is None or states[1] is None:
        return
    with open(get_conv_log_filename(), "a") as fout:
        data = {
            "tstamp": round(time.time(), 4),
            "type": vote_type,
            "models": [x for x in model_selectors],
            "states": [x.dict() for x in states],
            "ip": get_ip(request),
        }
        fout.write(json.dumps(data) + "\n")
    get_remote_logger().log(data)


def leftvote_last_response(
    state0, state1, model_selector0, model_selector1, request: gr.Request
):
    logger.info(f"leftvote (named). ip: {get_ip(request)}")
    vote_last_response(
        [state0, state1], "leftvote", [model_selector0, model_selector1], request
    )
    return ("",) + (disable_btn,) * 7


def rightvote_last_response(
    state0, state1, model_selector0, model_selector1, request: gr.Request
):
    logger.info(f"rightvote (named). ip: {get_ip(request)}")
    vote_last_response(
        [state0, state1], "rightvote", [model_selector0, model_selector1], request
    )
    return ("",) + (disable_btn,) * 7


def tievote_last_response(
    state0, state1, model_selector0, model_selector1, request: gr.Request
):
    logger.info(f"tievote (named). ip: {get_ip(request)}")
    vote_last_response(
        [state0, state1], "tievote", [model_selector0, model_selector1], request
    )
    return ("",) + (disable_btn,) * 7


def bothbad_vote_last_response(
    state0, state1, model_selector0, model_selector1, request: gr.Request
):
    logger.info(f"bothbad_vote (named). ip: {get_ip(request)}")
    vote_last_response(
        [state0, state1], "bothbad_vote", [model_selector0, model_selector1], request
    )
    return ("",) + (disable_btn,) * 7

def regenerate(state, request: gr.Request):
    ip = get_ip(request)
    logger.info(f"regenerate. ip: {ip}")
    if state is None:
        return (None, None, "") + (no_change_btn,) * 8
    if not state.regen_support:
        state.skip_next = True
        return (state, state.to_gradio_chatbot(), "", None) + (no_change_btn,) * 8
    state.conv.update_last_message(None)
    return (state, state.to_gradio_chatbot(), "") + (disable_btn,) * 8

def regenerate_multi(state0, state1, request: gr.Request):
    logger.info(f"regenerate (named). ip: {get_ip(request)}")
    states = [state0, state1]

    if state0 is None and state1 is not None:
        if not state1.regen_support:
            state1.skip_next = True
            return states + [None, state1.to_gradio_chatbot()] + [""] + [no_change_btn] * 8  
        state1.conv.update_last_message(None)
        return states + [None, state1.to_gradio_chatbot()] + [""] + [disable_btn] * 8

    if state1 is None and state0 is not None:
        if not state0.regen_support:
            state0.skip_next = True
            return states + [state0.to_gradio_chatbot(), None] + [""] + [no_change_btn] * 8    
        state0.conv.update_last_message(None)
        return states + [state0.to_gradio_chatbot(), None] + [""] + [disable_btn] * 8 
    
    if state0.regen_support and state1.regen_support:
        for i in range(num_sides):
            states[i].conv.update_last_message(None)
        return (
            states + [x.to_gradio_chatbot() for x in states] + [""] + [disable_btn] * 8
        )
    states[0].skip_next = True
    states[1].skip_next = True
    return states + [x.to_gradio_chatbot() for x in states] + [""] + [no_change_btn] * 8


def clear_history(sandbox_state0, sandbox_state1, request: gr.Request):
    logger.info(f"clear_history (named). ip: {get_ip(request)}")
    sandbox_states = [sandbox_state0, sandbox_state1]
    sandbox_state0["enabled_round"] = 0
    sandbox_state1["enabled_round"] = 0
    return (
        sandbox_states
        + [None] * num_sides
        + [None] * num_sides
        + [""]
        + [invisible_btn] * 4
        + [disable_btn] * 1
        + [invisible_btn] * 2
        + [disable_btn] * 1
        )
def clear_sandbox_components(*components):
    updates = []
    for component in components:
        updates.append(gr.update(value="", visible=False))
    return updates

def share_click(state0, state1, model_selector0, model_selector1, request: gr.Request):
    logger.info(f"share (named). ip: {get_ip(request)}")
    if state0 is not None and state1 is not None:
        vote_last_response(
            [state0, state1], "share", [model_selector0, model_selector1], request
        )

def update_sandbox_system_messages_multi(state0, state1, sandbox_state0, sandbox_state1, model_selector0, model_selector1):
    '''
    Add sandbox instructions to the system message.
    '''
    states = [state0, state1]
    model_selectors = [model_selector0, model_selector1]
    sandbox_states: list[ChatbotSandboxState] = [sandbox_state0, sandbox_state1]

    # Init states if necessary
    for i in range(num_sides):
        if states[i] is None:
            states[i] = State(model_selectors[i])
        sandbox_state = sandbox_states[i]
        if sandbox_state is None or sandbox_state['enable_sandbox'] is False or sandbox_state["enabled_round"] > 0:
            continue
        sandbox_state['enabled_round'] += 1 # avoid dup
        environment_instruction = sandbox_state['sandbox_instruction']
        current_system_message = states[i].conv.get_system_message(states[i].is_vision)
        new_system_message = f"{current_system_message}\n\n{environment_instruction}"
        states[i].conv.set_system_message(new_system_message)

    return states + [x.to_gradio_chatbot() for x in states]

def add_text_multi(
    state0, state1,
    model_selector0, model_selector1,
    sandbox_state0, sandbox_state1,
    text, request: gr.Request
):
    ip = get_ip(request)
    logger.info(f"add_text_multi (named). ip: {ip}. len: {len(text)}")
    states = [state0, state1]
    model_selectors = [model_selector0, model_selector1]
    sandbox_states = [sandbox_state0, sandbox_state1]

    # Init states if necessary
    for i in range(num_sides):
        if states[i] is None:
            states[i] = State(model_selectors[i])

    if len(text) <= 0:
        for i in range(num_sides):
            states[i].skip_next = True
        return (
            states
            + [x.to_gradio_chatbot() for x in states]
            + sandbox_states
            + ["", None]
            + [
                no_change_btn,
            ]
            * 8
        )

    model_list = [states[i].model_name for i in range(num_sides)]
    all_conv_text_left = states[0].conv.get_prompt()
    all_conv_text_right = states[1].conv.get_prompt()
    all_conv_text = (
        all_conv_text_left[-1000:] + all_conv_text_right[-1000:] + "\nuser: " + text
    )
    flagged = moderation_filter(all_conv_text, model_list)
    if flagged:
        logger.info(f"violate moderation (named). ip: {ip}. text: {text}")
        # overwrite the original text
        text = MODERATION_MSG

    conv = states[0].conv
    if (len(conv.messages) - conv.offset) // 2 >= CONVERSATION_TURN_LIMIT:
        logger.info(f"conversation turn limit. ip: {ip}. text: {text}")
        for i in range(num_sides):
            states[i].skip_next = True
        return (
            states
            + [x.to_gradio_chatbot() for x in states]
             + sandbox_states
            + [CONVERSATION_LIMIT_MSG]
            + [
                no_change_btn,
            ]
            * 8
        )

    text = text[:INPUT_CHAR_LEN_LIMIT]  # Hard cut-off
    for i in range(num_sides):
        states[i].conv.append_message(states[i].conv.roles[0], text)
        states[i].conv.append_message(states[i].conv.roles[1], None)
        states[i].skip_next = False

    return (
        states
        + [x.to_gradio_chatbot() for x in states]
        + sandbox_states
        + [""]
        + [disable_btn,] * 7
    )


def bot_response_multi(
    state0,
    state1,
    temperature,
    top_p,
    max_new_tokens,
    sandbox_state0,
    sandbox_state1,
    request: gr.Request,
):
    logger.info(f"bot_response_multi (named). ip: {get_ip(request)}")

    if state0 is not None and state1 is not None: 
        if state0.skip_next or state1.skip_next:
            # This generate call is skipped due to invalid inputs
            yield (
                state0,
                state1,
                state0.to_gradio_chatbot() ,
                state1.to_gradio_chatbot() ,
            ) + (no_change_btn,) * 8
            return

    states = [state0, state1]
    gen = []
    for i in range(num_sides):
        gen.append(
            bot_response(
                states[i],
                temperature,
                top_p,
                max_new_tokens,
                sandbox_state0,
                request
            )
        )

    model_tpy = []
    for i in range(num_sides):
        token_per_yield = 1
        if states[i] is not None and states[i].model_name in [
            "gemini-pro",
            "gemma-1.1-2b-it",
            "gemma-1.1-7b-it",
            "phi-3-mini-4k-instruct",
            "phi-3-mini-128k-instruct",
            "snowflake-arctic-instruct",
        ]:
            token_per_yield = 30
        elif states[i] is not None and states[i].model_name in [
            "qwen-max-0428",
            "qwen-vl-max-0809",
            "qwen1.5-110b-chat",
        ]:
            token_per_yield = 7
        elif states[i] is not None and  states[i].model_name in [
            "qwen2.5-72b-instruct",
            "qwen2-72b-instruct",
            "qwen-plus-0828",
            "qwen-max-0919",
            "llama-3.1-405b-instruct-bf16",
        ]:
            token_per_yield = 4
        model_tpy.append(token_per_yield)

    chatbots = [None] * num_sides
    iters = 0
    while True:
        stop = True
        iters += 1
        for i in range(num_sides):
            try:
                # yield fewer times if chunk size is larger
                if model_tpy[i] == 1 or (iters % model_tpy[i] == 1 or iters < 3):
                    ret = next(gen[i])
                    states[i], chatbots[i] = ret[0], ret[1]
                stop = False
            except StopIteration:
                pass
        yield states + chatbots + [disable_btn] * 8
        if stop:
            break


def flash_buttons():
    btn_updates = [
        [disable_btn] * 4 + [enable_btn] * 4,
        [enable_btn] * 8,
    ]
    for i in range(4):
        yield btn_updates[i % 2]
        time.sleep(0.3)


def build_side_by_side_ui_named(models):
    notice_markdown = f"""
## 📜 How It Works
- Interact with two chosen models (e.g., GPT, Gemini, Claude) as they generate programs with visual UIs.
- Test the programs in a sandbox environment, interact with their functionality, and vote for the better one!
- You can chat for multiple turns, explore the UIs, and continue testing until you identify a winner.
"""

    states = [gr.State() for _ in range(num_sides)]
    model_selectors = [None] * num_sides
    chatbots: list[gr.Chatbot | None] = [None] * num_sides

    with gr.Group(elem_id="share-region-named"):
        with gr.Row():
            for i in range(num_sides):
                with gr.Column():
                    model_selectors[i] = gr.Dropdown(
                        choices=models,
                        value=models[i] if len(models) > i else "",
                        label=f"Model {chr(ord('A') + i)}",
                        interactive=True,
                        show_label=True,
                        container=False,
                    )

        with gr.Row():
            for i in range(num_sides):
                label = "Model A" if i == 0 else "Model B"
                with gr.Column():
                    chatbots[i] = gr.Chatbot(
                        label=label,
                        elem_id=f"chatbot",
                        height=550,
                        show_copy_button=True,
                        latex_delimiters=[
                            {"left": "$", "right": "$", "display": False},
                            {"left": "$$", "right": "$$", "display": True},
                            {"left": r"\(", "right": r"\)", "display": False},
                            {"left": r"\[", "right": r"\]", "display": True},
                        ],
                    )


    # sandbox states and components
    sandbox_states: list[gr.State] = [] # state for each chatbot
    sandboxes_components: list[SandboxGradioSandboxComponents] = [] # components for each chatbot
    sandbox_hidden_components = []

    with gr.Group():
        with gr.Row():
            enable_sandbox_checkbox = gr.Checkbox(
                value=False,
                label="Enable Sandbox",
                info="Run generated code in a remote sandbox",
                interactive=True,
            )
            sandbox_env_choice = gr.Dropdown(choices=SUPPORTED_SANDBOX_ENVIRONMENTS, label="Sandbox Environment", interactive=True, visible=False)
        with gr.Group():
            with gr.Accordion("Sandbox & Output", open=True, visible=False) as sandbox_instruction_accordion:
                with gr.Group(visible=False) as sandbox_group:
                    sandbox_hidden_components.append(sandbox_group)
                    with gr.Row(visible=False) as sandbox_row:
                        sandbox_hidden_components.append(sandbox_row)
                        for chatbotIdx in range(num_sides):
                            with gr.Column(scale=1, visible=False) as column:
                                sandbox_state = gr.State(create_chatbot_sandbox_state(btn_list_length=8))
                                # Add containers for the sandbox output
                                sandbox_title = gr.Markdown(value=f"### Model {chatbotIdx + 1} Sandbox", visible=False)
    
                                with gr.Tab(label="Output", visible=False) as sandbox_output_tab:
                                    sandbox_output = gr.Markdown(value="", visible=False)
                                    sandbox_ui = SandboxComponent(
                                        value=("", ""),
                                        show_label=True,
                                        visible=False,
                                    )

                                with gr.Tab(label="Code", visible=False) as sandbox_code_tab:
                                    sandbox_code = gr.Code(
                                        value="",
                                        interactive=True, # allow user edit
                                        visible=False,
                                        # wrap_lines=True,
                                        label='Sandbox Code',
                                    )
                                    with gr.Row():
                                        sandbox_code_submit_btn = gr.Button(value="Apply Changes", visible=True, interactive=True, variant='primary', size='sm')
                                        # run code when click apply changes
                                        sandbox_code_submit_btn.click(
                                            fn=on_edit_code,
                                            inputs=[states[chatbotIdx], sandbox_state, sandbox_output, sandbox_ui, sandbox_code],
                                            outputs=[sandbox_output, sandbox_ui, sandbox_code]
                                        )

                                sandbox_states.append(sandbox_state)
                                sandboxes_components.append((
                                    sandbox_output,
                                    sandbox_ui,
                                    sandbox_code,
                                ))
                                sandbox_hidden_components.extend([column, sandbox_title, sandbox_output_tab, sandbox_code_tab])

        sandbox_hidden_components.extend([sandbox_env_choice, sandbox_instruction_accordion])

        sandbox_env_choice.change(
            fn=update_sandbox_config_multi,
            inputs=[
                enable_sandbox_checkbox,
                sandbox_env_choice,
                *sandbox_states
            ],
            outputs=[*sandbox_states]
        )

        # update sandbox global config
        enable_sandbox_checkbox.change(
            fn=update_visibility,
            inputs=[enable_sandbox_checkbox],
            outputs=sandbox_hidden_components
        ).then(            
            fn=update_sandbox_config_multi,
            inputs=[
                enable_sandbox_checkbox,
                sandbox_env_choice,
                *sandbox_states
            ],
            outputs=[*sandbox_states]
        )

    # First define all UI components
    with gr.Row():
        textbox = gr.Textbox(
            show_label=False,
            placeholder="👉 Enter your prompt and press ENTER",
            elem_id="input_box",
        )
        send_btn = gr.Button(value="Send", variant="primary", scale=0)
        send_btn_left = gr.Button(value="Send to Left", variant="primary", scale=0)
        send_btn_right = gr.Button(value="Send to Right", variant="primary", scale=0)
        send_btns_one_side = [send_btn_left, send_btn_right]

    with gr.Row():
        leftvote_btn = gr.Button(
            value="👈  A is better", visible=False, interactive=False
        )
        rightvote_btn = gr.Button(
            value="👉  B is better", visible=False, interactive=False
        )
        tie_btn = gr.Button(value="🤝  Tie", visible=False, interactive=False)
        bothbad_btn = gr.Button(
            value="👎  Both are bad", visible=False, interactive=False
        )

    with gr.Row() as button_row:
        clear_btn = gr.Button(value="🗑️  Clear history", interactive=False)
        regenerate_btn = gr.Button(value="🔄  Regenerate", interactive=False)
        left_regenerate_btn = gr.Button(value="🔄  Regenerate Left", interactive=False, visible=False)
        right_regenerate_btn = gr.Button(value="🔄  Regenerate Right", interactive=False, visible=False)
        share_btn = gr.Button(value="📷  Share")
        regenerate_one_side_btns = [left_regenerate_btn, right_regenerate_btn]

    # Define btn_list after all buttons are created
    btn_list = [
        leftvote_btn,
        rightvote_btn,
        tie_btn,
        bothbad_btn,
        regenerate_btn,
        left_regenerate_btn,
        right_regenerate_btn,
        clear_btn,
    ]

    with gr.Accordion("System Prompt", open=False) as system_prompt_accordion:
        system_prompt_textbox = gr.Textbox(
            value=DEFAULT_SANDBOX_INSTRUCTIONS[SandboxEnvironment.AUTO],
            show_label=False,
            lines=15,
            placeholder="Edit system prompt here",
            interactive=True,
            elem_id="system_prompt_box",
        )

    with gr.Accordion("Parameters", open=False) as parameter_row:
        temperature = gr.Slider(
            minimum=0.0,
            maximum=1.0,
            value=0.7,
            step=0.1,
            interactive=True,
            label="Temperature",
        )
        top_p = gr.Slider(
            minimum=0.0,
            maximum=1.0,
            value=1.0,
            step=0.1,
            interactive=True,
            label="Top P",
        )
        max_output_tokens = gr.Slider(
            minimum=16,
            maximum=2048,
            value=1024,
            step=64,
            interactive=True,
            label="Max output tokens",
        )

    notice = gr.Markdown(notice_markdown, elem_id="notice_markdown")
    gr.Markdown("## Supported Models")
    with gr.Accordion(
        f"🔍 Expand to see the descriptions of {len(models)} models", open=False
    ):
        model_description_md = get_model_description_md(models)
        gr.Markdown(model_description_md, elem_id="model_description_markdown")

    gr.Markdown(acknowledgment_md, elem_id="ack_markdown")
    
    # Define helper functions for system prompt updates
    def update_system_prompt_both(system_prompt, sandbox_state0, sandbox_state1):
        if sandbox_state0['enabled_round'] == 0:
            sandbox_state0['sandbox_instruction'] = system_prompt
        if sandbox_state1['enabled_round'] == 0:
            sandbox_state1['sandbox_instruction'] = system_prompt
        return sandbox_state0, sandbox_state1

    # Register event handlers
    textbox.submit(
        update_system_prompt_both,
        inputs=[system_prompt_textbox, sandbox_states[0], sandbox_states[1]],
        outputs=[sandbox_states[0], sandbox_states[1]]
    ).then(
        add_text_multi,
        states + model_selectors + sandbox_states + [textbox],
        states + chatbots + sandbox_states + [textbox] + btn_list[:7],
    ).then(
        update_sandbox_system_messages_multi,
        states + sandbox_states + model_selectors,
        states + chatbots
    ).then(
        bot_response_multi,
        states + [temperature, top_p, max_output_tokens] + sandbox_states,
        states + chatbots + btn_list,
    ).then(
        flash_buttons, [], btn_list
    ).then(
        lambda sandbox_state: gr.update(interactive=sandbox_state['enabled_round'] == 0),
        inputs=[sandbox_states[0]],
        outputs=[sandbox_env_choice]
    )

    send_btn.click(
        update_system_prompt_both,
        inputs=[system_prompt_textbox, sandbox_states[0], sandbox_states[1]],
        outputs=[sandbox_states[0], sandbox_states[1]]
    ).then(
        add_text_multi,
        states + model_selectors + sandbox_states + [textbox],
        states + chatbots + sandbox_states + [textbox] + btn_list[:7],
    ).then(
        update_sandbox_system_messages_multi,
        states + sandbox_states + model_selectors,
        states + chatbots
    ).then(
        bot_response_multi,
        states + [temperature, top_p, max_output_tokens] + sandbox_states,
        states + chatbots + btn_list,
    ).then(
        flash_buttons, [], btn_list
    ).then(
        lambda sandbox_state: gr.update(interactive=sandbox_state['enabled_round'] == 0),
        inputs=[sandbox_states[0]],
        outputs=[sandbox_env_choice]
    )

    # Register handlers for one-sided sends
    for chatbotIdx in range(num_sides):
        send_btns_one_side[chatbotIdx].click(
            update_system_prompt_both,
            inputs=[system_prompt_textbox, sandbox_states[0], sandbox_states[1]],
            outputs=[sandbox_states[0], sandbox_states[1]]
        ).then(
            add_text,
            [states[chatbotIdx], model_selectors[chatbotIdx], sandbox_states[chatbotIdx], textbox],
            [states[chatbotIdx], chatbots[chatbotIdx], textbox] + btn_list[:7],
        ).then(
            update_sandbox_system_message,
            [states[chatbotIdx], sandbox_states[chatbotIdx], model_selectors[chatbotIdx]],
            [states[chatbotIdx], chatbots[chatbotIdx]]
        ).then(
            bot_response,
            [states[chatbotIdx], temperature, top_p, max_output_tokens, sandbox_states[chatbotIdx]],
            [states[chatbotIdx], chatbots[chatbotIdx]] + btn_list,
        ).then(
            flash_buttons, [], btn_list
        ).then(
            lambda sandbox_state: gr.update(interactive=sandbox_state['enabled_round'] == 0),
            inputs=[sandbox_states[chatbotIdx]],
            outputs=[sandbox_env_choice]
        )

        # Register regenerate handlers
        regenerate_one_side_btns[chatbotIdx].click(
            regenerate, 
            states[chatbotIdx], 
            [states[chatbotIdx], chatbots[chatbotIdx], textbox] + btn_list
        ).then(
            bot_response,
            [states[chatbotIdx], temperature, top_p, max_output_tokens, sandbox_states[chatbotIdx]],
            [states[chatbotIdx], chatbots[chatbotIdx]] + btn_list,
        )

        # Register sandbox click handlers
        chatbots[chatbotIdx].select(
            fn=on_click_code_message_run,
            inputs=[states[chatbotIdx], sandbox_states[chatbotIdx], *sandboxes_components[chatbotIdx]],
            outputs=[*sandboxes_components[chatbotIdx]],
        )

    # Register model selector change handlers
    for i in range(num_sides):
        model_selectors[i].change(
            clear_history, 
            sandbox_states, 
            sandbox_states + states + chatbots + [textbox] + btn_list 
        ).then(
            clear_sandbox_components,
            inputs=[component for components in sandboxes_components for component in components],
            outputs=[component for components in sandboxes_components for component in components]
        ).then(
            lambda: gr.update(interactive=True),
            outputs=[sandbox_env_choice]
        )

    # Register share button handler
    share_js = """
function (a, b, c, d) {
    const captureElement = document.querySelector('#share-region-named');
    html2canvas(captureElement)
        .then(canvas => {
            canvas.style.display = 'none'
            document.body.appendChild(canvas)
            return canvas
        })
        .then(canvas => {
            const image = canvas.toDataURL('image/png')
            const a = document.createElement('a')
            a.setAttribute('download', 'chatbot-arena.png')
            a.setAttribute('href', image)
            a.click()
            canvas.remove()
        });
    return [a, b, c, d];
}
"""
    share_btn.click(share_click, states + model_selectors, [], js=share_js)

    # Register regenerate and clear button handlers
    regenerate_btn.click(
        regenerate_multi, states, states + chatbots + [textbox] + btn_list
    ).then(
        bot_response_multi,
        states + [temperature, top_p, max_output_tokens] + sandbox_states,
        states + chatbots + btn_list,
    ).then(
        flash_buttons, [], btn_list
    )

    clear_btn.click(
        clear_history, 
        sandbox_states, 
        sandbox_states + states + chatbots + [textbox] + btn_list
    ).then(
        clear_sandbox_components,
        inputs=[component for components in sandboxes_components for component in components],
        outputs=[component for components in sandboxes_components for component in components]
    ).then(
        lambda: gr.update(interactive=True),
        outputs=[sandbox_env_choice]
    )

    # Register voting button handlers
    leftvote_btn.click(
        leftvote_last_response,
        states + model_selectors,
        [textbox, leftvote_btn, rightvote_btn, tie_btn, bothbad_btn, send_btn, send_btn_left, send_btn_right]
    )

    rightvote_btn.click(
        rightvote_last_response,
        states + model_selectors,
        [textbox, leftvote_btn, rightvote_btn, tie_btn, bothbad_btn, send_btn, send_btn_left, send_btn_right]
    )

    tie_btn.click(
        tievote_last_response,
        states + model_selectors,
        [textbox, leftvote_btn, rightvote_btn, tie_btn, bothbad_btn, send_btn, send_btn_left, send_btn_right]
    )

    bothbad_btn.click(
        bothbad_vote_last_response,
        states + model_selectors,
        [textbox, leftvote_btn, rightvote_btn, tie_btn, bothbad_btn, send_btn, send_btn_left, send_btn_right]
    )

    return states + model_selectors