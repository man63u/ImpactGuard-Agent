from pathlib import Path
from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger

repo_root = str(Path(__file__).resolve().parent / "fixture_a")
config = MultilspyConfig.from_dict({"code_language": "python"})
lsp = SyncLanguageServer.create(config, MultilspyLogger(), repo_root)

with lsp.start_server():
    # main.py 行列数（0-indexed）：
    # row=0: "from lib import helper"
    # row=1: ""
    # row=2: ""
    # row=3: "def caller():"
    # row=4: "    return helper()"
    #        0123456789012345678
    #                   ^ col=11 是 helper 的第一个字母 h
    print("=== request_definition (从main.py的调用点查lib.py的定义) ===")
    defn = lsp.request_definition("main.py", 4, 11)
    print(repr(defn))
    print(type(defn))
    if defn:
        item = defn[0] if isinstance(defn, list) else defn
        print("keys:", list(item.keys()) if hasattr(item, 'keys') else dir(item))

    # lib.py 行列数（0-indexed）：
    # row=0: "def helper():"
    #        01234567
    #            ^ col=4 是 helper 的第一个字母 h
    print("\n=== request_references (从lib.py的定义点查所有调用方) ===")
    refs = lsp.request_references("lib.py", 0, 4)
    print(repr(refs))
    print(type(refs))
    if refs:
        item = refs[0] if isinstance(refs, list) else refs
        print("first item keys:", list(item.keys()) if hasattr(item, 'keys') else dir(item))
