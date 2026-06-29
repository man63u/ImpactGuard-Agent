from pathlib import Path
from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger

repo_root = str(Path(__file__).resolve().parent / "fixture_b")
config = MultilspyConfig.from_dict({"code_language": "python"})
lsp = SyncLanguageServer.create(config, MultilspyLogger(), repo_root)

with lsp.start_server():
    # app.py 行列数（0-indexed）：
    # row=0: "from flask import Flask"
    # row=1: ""
    # row=2: "app = Flask(__name__)"
    # row=3: ""
    # row=4: ""
    # row=5: "@app.route("/health")"
    # row=6: "def health_check():"
    #        0123456789
    #            ^ col=4 是 health_check 的第一个字母 h
    # row=7: "    return "ok""
    print("=== request_references on health_check ===")
    refs = lsp.request_references("app.py", 6, 4)
    print(repr(refs))
    print(f"type: {type(refs)}")
    print(f"count: {len(refs) if refs else 0}")
    if refs:
        for i, ref in enumerate(refs):
            print(f"  ref[{i}]: {repr(ref)}")
