'''
Run generated code in a sandbox environment.
'''

from enum import StrEnum
from typing import Any, Generator, TypeAlias, TypedDict, Set
import gradio as gr
import re
import os
import base64
from e2b import Sandbox
from e2b_code_interpreter import Sandbox as CodeSandbox
from gradio_sandboxcomponent import SandboxComponent
import ast
import subprocess
import json
from tempfile import NamedTemporaryFile
from tree_sitter import Language, Node, Parser
import tree_sitter_javascript
import tree_sitter_typescript
from pathlib import Path
import sys

E2B_API_KEY = os.environ.get("E2B_API_KEY")
'''
API key for the e2b API.
'''

class SandboxEnvironment(StrEnum):
    AUTO = 'Auto'
    # Code Interpreter
    PYTHON_CODE_INTERPRETER = 'Python Code Interpreter'
    JAVASCRIPT_CODE_INTERPRETER = 'Javascript Code Interpreter'
    # Web UI Frameworks
    HTML = 'HTML'
    REACT = 'React'
    VUE = 'Vue'
    GRADIO = 'Gradio'
    STREAMLIT = 'Streamlit'
    NICEGUI = 'NiceGUI'
    PYGAME = 'PyGame'


SUPPORTED_SANDBOX_ENVIRONMENTS: list[str] = [
    env.value for env in SandboxEnvironment
]

WEB_UI_SANDBOX_ENVIRONMENTS = [
    SandboxEnvironment.HTML,
    SandboxEnvironment.REACT,
    SandboxEnvironment.VUE,
    SandboxEnvironment.GRADIO,
    SandboxEnvironment.STREAMLIT,
    SandboxEnvironment.NICEGUI,
    SandboxEnvironment.PYGAME,
]

VALID_GRADIO_CODE_LANGUAGES = [
    'python', 'c', 'cpp', 'markdown', 'json', 'html', 'css', 'javascript', 'jinja2', 'typescript', 'yaml', 'dockerfile', 'shell', 'r', 'sql',
    'sql-msSQL', 'sql-mySQL', 'sql-mariaDB', 'sql-sqlite', 'sql-cassandra', 'sql-plSQL', 'sql-hive', 'sql-pgSQL', 'sql-gql', 'sql-gpSQL', 'sql-sparkSQL', 
    'sql-esper'
]
'''
Languages that gradio code component can render.
'''

RUN_CODE_BUTTON_HTML = "<button style='background-color: #4CAF50; border: none; color: white; padding: 10px 24px; text-align: center; text-decoration: none; display: inline-block; font-size: 16px; margin: 4px 2px; cursor: pointer; border-radius: 12px;'>Click to Run in Sandbox</button>"
'''
Button in the chat to run the code in the sandbox.
'''

GENERAL_SANDBOX_INSTRUCTION = """ You are an expert Software Engineer. Generate code for a single file to be executed in a sandbox. Do not import external files. You can output information if needed.

The code must be in the markdown format:
```<language>
<code>
```

If python or npm packages are needed, you have to explicitly output the required packages in the markdown format:
***REMOTE SANDBOX PACKAGES***:
```
pip install <package1> <package2> ...
npm install <package1> <package2> ...
```

The optional sandbox packages cell must be output together with the code cell in the same message. You should not only output the sandbox packages cell.
"""

DEFAULT_PYTHON_CODE_INTERPRETER_INSTRUCTION = """
Generate self-contained Python code for execution in a code interpreter.
There are standard and pre-installed libraries: aiohttp, beautifulsoup4, bokeh, gensim, imageio, joblib, librosa, matplotlib, nltk, numpy, opencv-python, openpyxl, pandas, plotly, pytest, python-docx, pytz, requests, scikit-image, scikit-learn, scipy, seaborn, soundfile, spacy, textblob, tornado, urllib3, xarray, xlrd, sympy.
Output via stdout, stderr, or render images, plots, and tables.
"""

DEFAULT_JAVASCRIPT_CODE_INTERPRETER_INSTRUCTION = """
Generate JavaScript code suitable for execution in a code interpreter environment. This is not for web page apps.
Ensure the code is self-contained and does not rely on browser-specific APIs.
You can output in stdout, stderr, or render images, plots, and tables.
"""

DEFAULT_HTML_SANDBOX_INSTRUCTION = """
Generate HTML code for a single vanilla HTML file to be executed in a sandbox. You can add style and javascript.
"""

DEFAULT_REACT_SANDBOX_INSTRUCTION = """ Generate typescript for a single-file Next.js 13+ React component tsx file. Pre-installed libs: ["nextjs@14.2.5", "typescript", "@types/node", "@types/react", "@types/react-dom", "postcss", "tailwindcss", "shadcn"] """
'''
Default sandbox prompt instruction.
'''

DEFAULT_VUE_SANDBOX_INSTRUCTION = """ Generate TypeScript for a single-file Vue.js 3+ component (SFC) in .vue format. The component should be a simple custom page in a styled `<div>` element. Do not include <NuxtWelcome /> or reference any external components. Surround the code with ``` in markdown. Pre-installed libs: ["nextjs@14.2.5", "typescript", "@types/node", "@types/react", "@types/react-dom", "postcss", "tailwindcss", "shadcn"], """
'''
Default sandbox prompt instruction for vue.
'''

DEFAULT_PYGAME_SANDBOX_INSTRUCTION = (
'''
Generate a pygame code snippet for a single file.
Write pygame main method in async function like:
```python
import asyncio
import pygame

async def main():
    global game_state
    while game_state:
        game_state(pygame.event.get())
        pygame.display.update()
        await asyncio.sleep(0) # it must be called on every frame

if __name__ == "__main__":
    asyncio.run(main())
```
'''
)

DEFAULT_GRADIO_SANDBOX_INSTRUCTION = """
Generate Python code for a single-file Gradio application using the Gradio library.
"""

DEFAULT_NICEGUI_SANDBOX_INSTRUCTION = """
Generate a Python NiceGUI code snippet for a single file.
"""

DEFAULT_STREAMLIT_SANDBOX_INSTRUCTION = """
Generate Python code for a single-file Streamlit application using the Streamlit library.
The app should automatically reload when changes are made. 
"""

AUTO_SANDBOX_INSTRUCTION = (
"""
You are an expert Software Engineer. Generate code for a single file to be executed in a sandbox. Do not import external files. You can output information if needed. 

The code should be in the markdown format:
```<language>
<code>
```

You can choose from the following sandbox environments:
"""
+ 'Sandbox Environment Name: ' + SandboxEnvironment.PYTHON_CODE_INTERPRETER + '\n' + DEFAULT_PYTHON_CODE_INTERPRETER_INSTRUCTION.strip() + '\n------\n'
+ 'Sandbox Environment Name: ' + SandboxEnvironment.REACT + '\n' + DEFAULT_REACT_SANDBOX_INSTRUCTION.strip() + '\n------\n'
+ 'Sandbox Environment Name: ' + SandboxEnvironment.VUE + '\n' + DEFAULT_VUE_SANDBOX_INSTRUCTION.strip() + '\n------\n'
+ 'Sandbox Environment Name: ' + SandboxEnvironment.JAVASCRIPT_CODE_INTERPRETER + '\n' + DEFAULT_JAVASCRIPT_CODE_INTERPRETER_INSTRUCTION.strip() + '\n------\n'
+ 'Sandbox Environment Name: ' + SandboxEnvironment.HTML + '\n' + DEFAULT_HTML_SANDBOX_INSTRUCTION.strip() + '\n------\n'
+ 'Sandbox Environment Name: ' + SandboxEnvironment.GRADIO + '\n' + DEFAULT_GRADIO_SANDBOX_INSTRUCTION.strip() + '\n------\n'
+ 'Sandbox Environment Name: ' + SandboxEnvironment.STREAMLIT + '\n' + DEFAULT_STREAMLIT_SANDBOX_INSTRUCTION.strip() + '\n------\n'
+ 'Sandbox Environment Name: ' + SandboxEnvironment.NICEGUI + '\n' + DEFAULT_NICEGUI_SANDBOX_INSTRUCTION.strip() + '\n------\n'
+ 'Sandbox Environment Name: ' + SandboxEnvironment.PYGAME + '\n' + DEFAULT_PYGAME_SANDBOX_INSTRUCTION.strip() + '\n------\n'
)

DEFAULT_SANDBOX_INSTRUCTIONS: dict[SandboxEnvironment, str] = {
    SandboxEnvironment.AUTO: AUTO_SANDBOX_INSTRUCTION.strip(),
    SandboxEnvironment.PYTHON_CODE_INTERPRETER: GENERAL_SANDBOX_INSTRUCTION + DEFAULT_PYTHON_CODE_INTERPRETER_INSTRUCTION.strip(),
    SandboxEnvironment.JAVASCRIPT_CODE_INTERPRETER: GENERAL_SANDBOX_INSTRUCTION + DEFAULT_JAVASCRIPT_CODE_INTERPRETER_INSTRUCTION.strip(),
    SandboxEnvironment.HTML: GENERAL_SANDBOX_INSTRUCTION + DEFAULT_HTML_SANDBOX_INSTRUCTION.strip(),
    SandboxEnvironment.REACT: GENERAL_SANDBOX_INSTRUCTION + DEFAULT_REACT_SANDBOX_INSTRUCTION.strip(),
    SandboxEnvironment.VUE: GENERAL_SANDBOX_INSTRUCTION + DEFAULT_VUE_SANDBOX_INSTRUCTION.strip(),
    SandboxEnvironment.GRADIO: GENERAL_SANDBOX_INSTRUCTION + DEFAULT_GRADIO_SANDBOX_INSTRUCTION.strip(),
    SandboxEnvironment.STREAMLIT: GENERAL_SANDBOX_INSTRUCTION + DEFAULT_STREAMLIT_SANDBOX_INSTRUCTION.strip(),
    SandboxEnvironment.NICEGUI: GENERAL_SANDBOX_INSTRUCTION + DEFAULT_NICEGUI_SANDBOX_INSTRUCTION.strip(),
    SandboxEnvironment.PYGAME: GENERAL_SANDBOX_INSTRUCTION + DEFAULT_PYGAME_SANDBOX_INSTRUCTION.strip(),
}


SandboxGradioSandboxComponents: TypeAlias =  tuple[
    gr.Markdown | Any,  # sandbox_output
    SandboxComponent | Any,  # sandbox_ui
    gr.Code | Any,  # sandbox_code
]
'''
Gradio components for the sandbox.
'''

class ChatbotSandboxState(TypedDict):
    '''
    Chatbot sandbox state in gr.state.
    '''
    enable_sandbox: bool
    '''
    Whether the code sandbox is enabled.
    '''
    sandbox_instruction: str | None
    '''
    The sandbox instruction to display.
    '''
    enabled_round: int
    '''
    The chat round after which the sandbox is enabled.
    '''
    sandbox_environment: SandboxEnvironment | None
    '''
    The sandbox environment to run the code.
    '''
    auto_selected_sandbox_environment: SandboxEnvironment | None
    '''
    The sandbox environment selected automatically.
    '''
    code_to_execute: str | None
    '''
    The code to execute in the sandbox.
    '''
    code_language: str | None
    '''
    The code language to execute in the sandbox.
    '''
    code_dependencies: tuple[list[str], list[str]]
    '''
    The code dependencies for the sandbox (python, npm).
    '''
    btn_list_length: int | None


def create_chatbot_sandbox_state(btn_list_length: int) -> ChatbotSandboxState:
    '''
    Create a new chatbot sandbox state.
    '''
    return {
        "enable_sandbox": False,
        "sandbox_environment": None,
        "auto_selected_sandbox_environment": None,
        "sandbox_instruction": None,
        "code_to_execute": "",
        "code_language": None,
        "code_dependencies": ([], []),
        "enabled_round": 0,
        "btn_list_length": btn_list_length
    }


def update_sandbox_config_multi(
    enable_sandbox: bool,
    sandbox_environment: SandboxEnvironment,
    *states: ChatbotSandboxState
) -> list[ChatbotSandboxState]:
    '''
    Fn to update sandbox config.
    '''
    return [
        update_sandbox_config(enable_sandbox, sandbox_environment, state) 
        for state
        in states
    ]

def update_sandbox_config(
    enable_sandbox: bool,
    sandbox_environment: SandboxEnvironment,
    state: ChatbotSandboxState
) -> ChatbotSandboxState:
    '''
    Fn to update sandbox config for single model.
    '''
    state["enable_sandbox"] = enable_sandbox
    state["sandbox_environment"] = sandbox_environment
    state['sandbox_instruction'] = DEFAULT_SANDBOX_INSTRUCTIONS.get(sandbox_environment, None)
    return state


def update_visibility(visible):
    return [gr.update(visible=visible)] *12


def update_visibility_for_single_model(visible: bool, component_cnt: int):
    return [gr.update(visible=visible)] * component_cnt


def extract_python_imports(code: str) -> list[str]:
    '''
    Extract Python package imports using AST parsing.
    Returns a list of top-level package names.
    Handles:
    - Regular imports: import foo, import foo.bar
    - From imports: from foo import bar, from foo.bar import baz
    - Multiple imports: import foo, bar
    - Aliased imports: import foo as bar, from foo import bar as baz
    - Star imports: from foo import *
    - Relative imports are ignored
    '''
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    packages: Set[str] = set()
    
    for node in ast.walk(tree):
        try:
            if isinstance(node, ast.Import):
                for name in node.names:
                    # Get the top-level package name from any dotted path
                    # e.g., 'foo.bar.baz' -> 'foo'
                    if name.name:  # Ensure there's a name
                        packages.add(name.name.split('.')[0])
                        
            elif isinstance(node, ast.ImportFrom):
                # Skip relative imports (those starting with dots)
                if node.level == 0 and node.module:
                    # Get the top-level package name
                    # e.g., from foo.bar import baz -> 'foo'
                    packages.add(node.module.split('.')[0])
                    
            # Also check for common dynamic import patterns
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id == 'importlib':
                    # Handle importlib.import_module('package')
                    if len(node.args) > 0 and isinstance(node.args[0], ast.Str):
                        packages.add(node.args[0].s.split('.')[0])
                elif isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                    # Handle __import__('package') and importlib.import_module('package')
                    if node.func.value.id == 'importlib' and node.func.attr == 'import_module':
                        if len(node.args) > 0 and isinstance(node.args[0], ast.Str):
                            packages.add(node.args[0].s.split('.')[0])
                    elif node.func.attr == '__import__':
                        if len(node.args) > 0 and isinstance(node.args[0], ast.Str):
                            packages.add(node.args[0].s.split('.')[0])
        except Exception as e:
            print(f"Error processing node {type(node)}: {e}")
            continue
    
    # Filter out standard library modules using sys.stdlib_module_names
    std_libs = set(sys.stdlib_module_names)
    
    # Also filter out known pre-installed packages
    preinstalled = {'pygame', 'gradio', 'streamlit', 'nicegui'}
    
    return list(packages - std_libs - preinstalled)

def extract_js_imports(code: str) -> list[str]:
    '''
    Extract npm package imports using Tree-sitter for robust parsing.
    Handles both JavaScript and TypeScript code.
    Returns a list of package names.
    '''
    try:
        # Initialize parsers with language modules
        ts_parser = Parser()
        js_parser = Parser()
        ts_parser.set_language(Language(tree_sitter_typescript.language()))
        js_parser.set_language(Language(tree_sitter_javascript.language()))
        
        # Try parsing as TypeScript first, then JavaScript
        code_bytes = bytes(code, "utf8")
        try:
            tree = ts_parser.parse(code_bytes)
        except:
            try:
                tree = js_parser.parse(code_bytes)
            except:
                return []
        
        packages: Set[str] = set()
        
        def visit_node(node: Node) -> None:
            if node.type == 'import_statement':
                # Handle ES6 imports
                string_node = node.child_by_field_name('source')
                if string_node and string_node.type in ['string', 'string_fragment']:
                    pkg_path = code[string_node.start_byte:string_node.end_byte].strip('"\'')
                    if not pkg_path.startswith('.'):
                        packages.add(pkg_path.split('/')[0])
                        
            elif node.type == 'call_expression':
                # Handle require calls
                func_node = node.child_by_field_name('function')
                if func_node and func_node.text and func_node.text.decode('utf8') == 'require':
                    args = node.child_by_field_name('arguments')
                    if args and args.named_children:
                        arg = args.named_children[0]
                        if arg.type in ['string', 'string_fragment']:
                            pkg_path = code[arg.start_byte:arg.end_byte].strip('"\'')
                            if not pkg_path.startswith('.'):
                                packages.add(pkg_path.split('/')[0])
            
            # Recursively visit children
            for child in node.children:
                visit_node(child)
        
        visit_node(tree.root_node)
        return list(packages)
        
    except Exception as e:
        print(f"Tree-sitter parsing failed: {e}")
        # Fallback to basic regex parsing if tree-sitter fails
        lines = code.split('\n')
        packages: Set[str] = set()
        
        for line in lines:
            line = line.strip()
            # Match ES6 imports
            if line.startswith('import '):
                matches = re.findall(r'[\'"]([@\w-]+(?:/[\w-]+)?)[\'"]', line)
                packages.update(matches)
            # Match require statements
            elif 'require(' in line:
                matches = re.findall(r'require\([\'"](@?\w+(?:/\w+)?)[\'"]', line)
                packages.update(matches)
        
        return [pkg.split('/')[0] for pkg in packages if pkg.startswith('@') or '/' not in pkg]

def determine_python_environment(code: str, imports: list[str]) -> SandboxEnvironment | None:
    '''
    Determine Python sandbox environment based on imports and AST analysis.
    '''
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            # Check for specific framework usage patterns
            if isinstance(node, ast.Name) and node.id == 'gr':
                return SandboxEnvironment.GRADIO
            elif isinstance(node, ast.Name) and node.id == 'st':
                return SandboxEnvironment.STREAMLIT
    except SyntaxError:
        pass

    # Check imports for framework detection
    if 'pygame' in imports:
        return SandboxEnvironment.PYGAME
    elif 'gradio' in imports:
        return SandboxEnvironment.GRADIO
    elif 'streamlit' in imports:
        return SandboxEnvironment.STREAMLIT
    elif 'nicegui' in imports:
        return SandboxEnvironment.NICEGUI
    
    return SandboxEnvironment.PYTHON_CODE_INTERPRETER

def determine_js_environment(code: str, imports: list[str]) -> SandboxEnvironment | None:
    '''
    Determine JavaScript/TypeScript sandbox environment based on imports and AST analysis.
    '''
    try:
        # Initialize parser
        ts_parser = Parser()
        ts_parser.set_language(Language(tree_sitter_typescript.language()))
        
        # Parse the code
        tree = ts_parser.parse(bytes(code, "utf8"))
        
        def has_framework_patterns(node: Node) -> bool:
            # Check for React patterns
            if node.type in ['jsx_element', 'jsx_self_closing_element']:
                return True
            # Check for Vue template
            elif node.type == 'template_element':
                return True
            return False
        
        # Check for framework-specific patterns in the AST
        cursor = tree.walk()
        reached_end = False
        while not reached_end:
            if has_framework_patterns(cursor.node):
                if cursor.node.type.startswith('jsx'):
                    return SandboxEnvironment.REACT
                elif cursor.node.type == 'template_element':
                    return SandboxEnvironment.VUE
            
            reached_end = not cursor.goto_next_sibling()
            if reached_end and cursor.goto_parent():
                reached_end = not cursor.goto_next_sibling()
    
    except Exception:
        pass
    
    # Check imports for framework detection
    react_packages = {'react', '@react', 'next', '@next', 'vite'}
    vue_packages = {'vue', '@vue', 'nuxt', '@nuxt'}
    
    if any(pkg in react_packages for pkg in imports):
        return SandboxEnvironment.REACT
    elif any(pkg in vue_packages for pkg in imports):
        return SandboxEnvironment.VUE
    
    return SandboxEnvironment.JAVASCRIPT_CODE_INTERPRETER

def extract_code_from_markdown(message: str, enable_auto_env: bool=False) -> tuple[str, str, tuple[list[str], list[str]], SandboxEnvironment | None] | None:
    '''
    Extracts code from a markdown message by parsing code blocks directly.
    Determines sandbox environment based on code content and frameworks used.

    Returns:
        tuple[str, str, tuple[list[str], list[str]], SandboxEnvironment | None]: A tuple:
            1. code - the longest code block found
            2. code language
            3. sandbox python and npm dependencies (extracted using static analysis)
            4. sandbox environment determined from code content
    '''
    # Find all code blocks
    code_block_regex = r'```(?P<code_lang>\w+)?\n(?P<code>.*?)```'
    matches = list(re.finditer(code_block_regex, message, re.DOTALL))
    
    if not matches:
        return None
        
    # Find the longest code block
    longest_match = max(matches, key=lambda m: len(m.group('code')))
    code = longest_match.group('code').strip()
    code_lang = (longest_match.group('code_lang') or '').lower()
    
    # Extract package dependencies using static analysis
    python_packages: list[str] = []
    npm_packages: list[str] = []
    
    # Determine sandbox environment based on language and imports
    if code_lang in ['py', 'python']:
        python_packages = extract_python_imports(code)
        sandbox_env_name = determine_python_environment(code, python_packages)
    elif code_lang in ['js', 'javascript', 'ts', 'typescript', 'tsx', 'jsx']:
        npm_packages = extract_js_imports(code)
        sandbox_env_name = determine_js_environment(code, npm_packages)
    elif code_lang in ['html','xhtml', 'xml'] or ('<!DOCTYPE html>' in code or '<html' in code):
        sandbox_env_name = SandboxEnvironment.HTML
    else:
        sandbox_env_name = None

    if enable_auto_env and sandbox_env_name is None:
        return None

    return code, code_lang, (python_packages, npm_packages), sandbox_env_name


def render_result(result):
    if result.png:
        if isinstance(result.png, str):
            img_str = result.png
        else:
            img_str = base64.b64encode(result.png).decode()
        return f"![png image](data:image/png;base64,{img_str})"
    elif result.jpeg:
        if isinstance(result.jpeg, str):
            img_str = result.jpeg
        else:
            img_str = base64.b64encode(result.jpeg).decode()
        return f"![jpeg image](data:image/jpeg;base64,{img_str})"
    elif result.svg:
        if isinstance(result.svg, str):
            svg_data = result.svg
        else:
            svg_data = result.svg.decode()
        svg_base64 = base64.b64encode(svg_data.encode()).decode()
        return f"![svg image](data:image/svg+xml;base64,{svg_base64})"
    elif result.html:
        return result.html
    elif result.markdown:
        return f"```markdown\n{result.markdown}\n```"
    elif result.latex:
        return f"```latex\n{result.latex}\n```"
    elif result.json:
        return f"```json\n{result.json}\n```"
    elif result.javascript:
        return result.javascript  # Return raw JavaScript
    else:
        return str(result)

def install_pip_dependencies(sandbox: Sandbox, dependencies: list[str]):
    '''
    Install pip dependencies in the sandbox.
    '''
    if not dependencies:
        return
    sandbox.commands.run(
        f"uv pip install --system {' '.join(dependencies)}",
        timeout=60 * 3,
        on_stdout=lambda message: print(message),
        on_stderr=lambda message: print(message),
    )


def install_npm_dependencies(sandbox: Sandbox, dependencies: list[str]):
    '''
    Install npm dependencies in the sandbox.
    '''
    if not dependencies:
        return
    sandbox.commands.run(
        f"npm install {' '.join(dependencies)}",
        timeout=60 * 3,
        on_stdout=lambda message: print(message),
        on_stderr=lambda message: print(message),
    )


def run_code_interpreter(code: str, code_language: str | None, code_dependencies: tuple[list[str], list[str]]) -> str:
    """
    Executes the provided code within a sandboxed environment and returns the output.

    Args:
        code (str): The code to be executed.
    """
    sandbox = CodeSandbox(
        api_key=E2B_API_KEY,
    )

    sandbox.commands.run("pip install uv",
                         timeout=60 * 3,
                         on_stderr=lambda message: print(message),)
    
    python_dependencies, npm_dependencies = code_dependencies
    install_pip_dependencies(sandbox, python_dependencies)
    install_npm_dependencies(sandbox, npm_dependencies)

    execution = sandbox.run_code(
        code=code,
        language=code_language
    )

    # collect stdout, stderr from sandbox
    stdout = "\n".join(execution.logs.stdout)
    stderr = "\n".join(execution.logs.stderr)
    output = ""
    if stdout:
        output += f"### Stdout:\n```\n{stdout}\n```\n\n"
    if stderr:
        output += f"### Stderr:\n```\n{stderr}\n```\n\n"

    results = []
    js_code = ""
    for result in execution.results:
        rendered_result = render_result(result)
        if result.javascript:
            # TODO: js_code are not used
            # js_code += rendered_result + "\n"
            print("JavaScript code:", rendered_result)
        else:
            results.append(rendered_result)
    if results:
        output += "\n### Results:\n" + "\n".join(results)

    return output


def run_html_sandbox(code: str, code_dependencies: tuple[list[str], list[str]]) -> str:
    """
    Executes the provided code within a sandboxed environment and returns the output.

    Args:
        code (str): The code to be executed.

    Returns:
        url for remote sandbox
    """
    sandbox = Sandbox(
        api_key=E2B_API_KEY,
    )

    python_dependencies, npm_dependencies = code_dependencies
    install_pip_dependencies(sandbox, python_dependencies)
    install_npm_dependencies(sandbox, npm_dependencies)

    sandbox.files.make_dir('myhtml')
    file_path = "~/myhtml/main.html"
    sandbox.files.write(path=file_path, data=code, request_timeout=60)

    process = sandbox.commands.run(
        "python -m http.server 3000", background=True)  # start http server

    # get game server url
    host = sandbox.get_host(3000)
    url = f"https://{host}"
    return url + '/myhtml/main.html'


def run_react_sandbox(code: str, code_dependencies: tuple[list[str], list[str]]) -> str:
    """
    Executes the provided code within a sandboxed environment and returns the output.

    Args:
        code (str): The code to be executed.

    Returns:
        url for remote sandbox
    """
    sandbox = Sandbox(
        template="nextjs-developer",
        metadata={
            "template": "nextjs-developer"
        },
        api_key=E2B_API_KEY,
    )

    python_dependencies, npm_dependencies = code_dependencies
    install_pip_dependencies(sandbox, python_dependencies)
    install_npm_dependencies(sandbox, npm_dependencies)

    # set up the sandbox
    sandbox.files.make_dir('pages')
    file_path = "~/pages/index.tsx"
    sandbox.files.write(path=file_path, data=code, request_timeout=60)

    # get the sandbox url
    sandbox_url = 'https://' + sandbox.get_host(3000)
    return sandbox_url


def run_vue_sandbox(code: str, code_dependencies: tuple[list[str], list[str]]) -> str:
    """
    Executes the provided Vue code within a sandboxed environment and returns the output.

    Args:
        code (str): The Vue code to be executed.

    Returns:
        url for remote sandbox
    """
    sandbox = Sandbox(
        template="vue-developer",
        metadata={
            "template": "vue-developer"
        },
        api_key=E2B_API_KEY,
    )

    # Set up the sandbox
    file_path = "~/app.vue"
    sandbox.files.write(path=file_path, data=code, request_timeout=60)

    python_dependencies, npm_dependencies = code_dependencies
    install_pip_dependencies(sandbox, python_dependencies)
    install_npm_dependencies(sandbox, npm_dependencies)

    # Get the sandbox URL
    sandbox_url = 'https://' + sandbox.get_host(3000)
    return sandbox_url


def run_pygame_sandbox(code: str, code_dependencies: tuple[list[str], list[str]]) -> str:
    """
    Executes the provided code within a sandboxed environment and returns the output.

    Args:
        code (str): The code to be executed.

    Returns:
        url for remote sandbox
    """
    sandbox = Sandbox(
        api_key=E2B_API_KEY,
    )

    sandbox.files.make_dir('mygame')
    file_path = "~/mygame/main.py"
    sandbox.files.write(path=file_path, data=code, request_timeout=60)
    sandbox.commands.run("pip install uv",
                         timeout=60 * 3,
                         # on_stdout=lambda message: print(message),
                         on_stderr=lambda message: print(message),)
    sandbox.commands.run("uv pip install --system pygame pygbag black",
                         timeout=60 * 3,
                         # on_stdout=lambda message: print(message),
                         on_stderr=lambda message: print(message),)
    
    python_dependencies, npm_dependencies = code_dependencies
    install_pip_dependencies(sandbox, python_dependencies)
    install_npm_dependencies(sandbox, npm_dependencies)

    # build the pygame code
    sandbox.commands.run(
        "pygbag --build ~/mygame",  # build game
        timeout=60 * 5,
        # on_stdout=lambda message: print(message),
        # on_stderr=lambda message: print(message),
    )

    process = sandbox.commands.run(
        "python -m http.server 3000", background=True)  # start http server

    # get game server url
    host = sandbox.get_host(3000)
    url = f"https://{host}"
    return url + '/mygame/build/web/'


def run_nicegui_sandbox(code: str, code_dependencies: tuple[list[str], list[str]]) -> str:
    """
    Executes the provided code within a sandboxed environment and returns the output.

    Args:
        code (str): The code to be executed.

    Returns:
        url for remote sandbox
    """
    sandbox = Sandbox(
        api_key=E2B_API_KEY,
    )

    # set up sandbox
    setup_commands = [
        "pip install --upgrade nicegui",
    ]
    for command in setup_commands:
        sandbox.commands.run(
            command,
            timeout=60 * 3,
            on_stdout=lambda message: print(message),
            on_stderr=lambda message: print(message),
        )

    # write code to file
    sandbox.files.make_dir('mynicegui')
    file_path = "~/mynicegui/main.py"
    sandbox.files.write(path=file_path, data=code, request_timeout=60)

    python_dependencies, npm_dependencies = code_dependencies
    install_pip_dependencies(sandbox, python_dependencies)
    install_npm_dependencies(sandbox, npm_dependencies)

    process = sandbox.commands.run(
        "python ~/mynicegui/main.py", background=True)

    # get web gui url
    host = sandbox.get_host(port=8080)
    url = f"https://{host}"
    return url


def run_gradio_sandbox(code: str, code_dependencies: tuple[list[str], list[str]]) -> str:
    """
    Executes the provided code within a sandboxed environment and returns the output.

    Args:
        code (str): The code to be executed.

    Returns:
        url for remote sandbox
    """
    sandbox = Sandbox(
        template="gradio-developer",
        metadata={
            "template": "gradio-developer"
        },
        api_key=E2B_API_KEY,
    )

    # set up the sandbox
    file_path = "~/app.py"
    sandbox.files.write(path=file_path, data=code, request_timeout=60)

    python_dependencies, npm_dependencies = code_dependencies
    install_pip_dependencies(sandbox, python_dependencies)
    install_npm_dependencies(sandbox, npm_dependencies)

    # get the sandbox url
    sandbox_url = 'https://' + sandbox.get_host(7860)
    return sandbox_url


def run_streamlit_sandbox(code: str, code_dependencies: tuple[list[str], list[str]]) -> str:
    sandbox = Sandbox(api_key=E2B_API_KEY)

    setup_commands = ["pip install --upgrade streamlit"]

    for command in setup_commands:
        sandbox.commands.run(
            command,
            timeout=60 * 3,
            on_stdout=lambda message: print(message),
            on_stderr=lambda message: print(message),
        )

    sandbox.files.make_dir('mystreamlit')
    file_path = "~/mystreamlit/app.py"
    sandbox.files.write(path=file_path, data=code, request_timeout=60)

    python_dependencies, npm_dependencies = code_dependencies
    install_pip_dependencies(sandbox, python_dependencies)
    install_npm_dependencies(sandbox, npm_dependencies)

    process = sandbox.commands.run(
        "streamlit run ~/mystreamlit/app.py --server.port 8501 --server.headless true",
        background=True
    )

    host = sandbox.get_host(port=8501)
    url = f"https://{host}"
    return url

def on_edit_code(
    state,
    sandbox_state: ChatbotSandboxState,
    sandbox_output: gr.Markdown,
    sandbox_ui: SandboxComponent,
    sandbox_code: str,
) -> Generator[tuple[Any, Any, Any], None, None]:
    '''
    Gradio Handler when code is edited manually by users.
    '''
    if sandbox_state['enable_sandbox'] is False:
        yield None, None, None
        return
    if len(sandbox_code.strip()) == 0 or sandbox_code == sandbox_state['code_to_execute']:
        yield gr.skip(), gr.skip(), gr.skip()
        return
    sandbox_state['code_to_execute'] = sandbox_code
    yield from on_run_code(state, sandbox_state, sandbox_output, sandbox_ui, sandbox_code)

def on_click_code_message_run(
    state,
    sandbox_state: ChatbotSandboxState,
    sandbox_output: gr.Markdown,
    sandbox_ui: SandboxComponent,
    sandbox_code: str,
    evt: gr.SelectData
) -> Generator[SandboxGradioSandboxComponents, None, None]:
    '''
    Gradio Handler when run code button in message is clicked. Update Sandbox components.
    '''
    if sandbox_state['enable_sandbox'] is False:
        yield None, None, None
        return
    if not evt.value.endswith(RUN_CODE_BUTTON_HTML):
        yield gr.skip(), gr.skip(), gr.skip()
        return

    message = evt.value.replace(RUN_CODE_BUTTON_HTML, "").strip()
    extract_result = extract_code_from_markdown(
        message=message,
        enable_auto_env=sandbox_state['sandbox_environment'] == SandboxEnvironment.AUTO
    )
    if extract_result is None:
        yield gr.skip(), gr.skip(), gr.skip()
        return
    code, code_language, code_dependencies, env_selection = extract_result

    if sandbox_state['code_to_execute'] == code and sandbox_state['code_language'] == code_language and sandbox_state['code_dependencies'] == code_dependencies:
        # skip if no changes
        yield gr.skip(), gr.skip(), gr.skip()
        return

    if code_language == 'tsx':
        code_language = 'typescript'
    code_language = code_language.lower() if code_language and code_language.lower(
        # ensure gradio supports the code language
    ) in VALID_GRADIO_CODE_LANGUAGES else None

    sandbox_state['code_to_execute'] = code
    sandbox_state['code_language'] = code_language
    sandbox_state['code_dependencies'] = code_dependencies
    if sandbox_state['sandbox_environment'] == SandboxEnvironment.AUTO:
        sandbox_state['auto_selected_sandbox_environment'] = env_selection
    yield from on_run_code(state, sandbox_state, sandbox_output, sandbox_ui, sandbox_code)

def on_run_code(
    state,
    sandbox_state: ChatbotSandboxState,
    sandbox_output: gr.Markdown,
    sandbox_ui: SandboxComponent,
    sandbox_code: str
) -> Generator[tuple[Any, Any, Any], None, None]:
    '''
    gradio fn when run code button is clicked. Update Sandbox components.
    '''
    if sandbox_state['enable_sandbox'] is False:
        yield None, None, None
        return

    # validate e2b api key
    if not E2B_API_KEY:
        raise ValueError("E2B_API_KEY is not set in env vars.")

    code, code_language = sandbox_state['code_to_execute'], sandbox_state['code_language']
    if code is None or code_language is None:
        yield None, None, None
        return

    if code_language == 'tsx':
        code_language = 'typescript'
    code_language = code_language.lower() if code_language and code_language.lower(
        # ensure gradio supports the code language
    ) in VALID_GRADIO_CODE_LANGUAGES else None

    # show loading
    yield (
        gr.Markdown(value="### Loading Sandbox", visible=True),
        SandboxComponent(visible=False),
        gr.Code(value=code, language=code_language, visible=True),
    )

    sandbox_env = sandbox_state['sandbox_environment'] if sandbox_state['sandbox_environment'] != SandboxEnvironment.AUTO else sandbox_state['auto_selected_sandbox_environment']
    code_dependencies = sandbox_state['code_dependencies']

    match sandbox_env:
        case SandboxEnvironment.HTML:
            url = run_html_sandbox(code=code, code_dependencies=code_dependencies)
            yield (
                gr.Markdown(value="### Running Sandbox", visible=True),
                SandboxComponent(
                    value=(url, code),
                    label="Example",
                    visible=True,
                    key="newsandbox",
                ),
                gr.skip(),
            )
        case SandboxEnvironment.REACT:
            url = run_react_sandbox(code=code, code_dependencies=code_dependencies)
            yield (
                gr.Markdown(value="### Running Sandbox", visible=True),
                SandboxComponent(
                    value=(url, code),
                    label="Example",
                    visible=True,
                    key="newsandbox",
                ),
                gr.skip(),
            )
        case SandboxEnvironment.VUE:
            url = run_vue_sandbox(code=code, code_dependencies=code_dependencies)
            yield (
                gr.Markdown(value="### Running Sandbox", visible=True),
                SandboxComponent(
                    value=(url, code),
                    label="Example",
                    visible=True,
                    key="newsandbox",
                ),
                gr.skip(),
            )
        case SandboxEnvironment.PYGAME:
            url = run_pygame_sandbox(code=code, code_dependencies=code_dependencies)
            yield (
                gr.Markdown(value="### Running Sandbox", visible=True),
                SandboxComponent(
                    value=(url, code),
                    label="Example",
                    visible=True,
                    key="newsandbox",
                ),
                gr.skip(),
            )
        case SandboxEnvironment.GRADIO:
            url = run_gradio_sandbox(code=code, code_dependencies=code_dependencies)
            yield (
                gr.Markdown(value="### Running Sandbox", visible=True),
                SandboxComponent(
                    value=(url, code),
                    label="Example",
                    visible=True,
                    key="newsandbox",
                ),
                gr.skip(),
            )
        case SandboxEnvironment.STREAMLIT:
            url = run_streamlit_sandbox(code=code, code_dependencies=code_dependencies)
            yield (
                gr.Markdown(value="### Running Sandbox", visible=True),
                SandboxComponent(
                    value=(url, code),
                    label="Example",
                    visible=True,
                    key="newsandbox",
                ),
                gr.skip(),
            )
        case SandboxEnvironment.NICEGUI:
            url = run_nicegui_sandbox(code=code, code_dependencies=code_dependencies)
            yield (
                gr.Markdown(value="### Running Sandbox", visible=True),
                SandboxComponent(
                    value=(url, code),
                    label="Example",
                    visible=True,
                    key="newsandbox",
                ),
                gr.skip(),
            )
        case SandboxEnvironment.PYTHON_CODE_INTERPRETER:
            output = run_code_interpreter(
                code=code, code_language='python', code_dependencies=code_dependencies
            )
            yield (
                gr.Markdown(value=output, sanitize_html=False, visible=True),
                SandboxComponent(
                    value=('', ''),
                    label="Example",
                    visible=False,
                    key="newsandbox",
                ),  # hide the sandbox component
                gr.skip()
            )
        case SandboxEnvironment.JAVASCRIPT_CODE_INTERPRETER:
            output = run_code_interpreter(
                code=code, code_language='javascript', code_dependencies=code_dependencies
            )
            yield (
                gr.Markdown(value=output, visible=True),
                SandboxComponent(
                    value=('', ''),
                    label="Example",
                    visible=False,
                    key="newsandbox",
                ),  # hide the sandbox component
                gr.skip()
            )
        case _:
            raise ValueError(
                f"Unsupported sandbox environment: {sandbox_state['sandbox_environment']}")
