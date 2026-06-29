import urllib.parse
from pathlib import Path
from urllib.request import url2pathname
from multilspy import SyncLanguageServer
from multilspy.multilspy_config import MultilspyConfig
from multilspy.multilspy_logger import MultilspyLogger


def uri_to_relpath(uri: str, repo_root: Path) -> str:
    parsed = urllib.parse.urlparse(uri)
    abs_path = Path(url2pathname(parsed.path))
    return str(abs_path.relative_to(repo_root)).replace("\\", "/")


repo_root = Path(__file__).resolve().parent / "fixture_a"
config = MultilspyConfig.from_dict({"code_language": "python"})
lsp = SyncLanguageServer.create(config, MultilspyLogger(), str(repo_root))

with lsp.start_server():
    result = lsp.request_definition("main.py", 4, 11)
    raw_uri = result[0]['uri']
    print(f"原始uri: {raw_uri}")

    # 逐步调试
    parsed = urllib.parse.urlparse(raw_uri)
    print(f"urlparse.path: {parsed.path!r}")
    raw_path = url2pathname(parsed.path)
    print(f"url2pathname结果: {raw_path!r}")
    abs_path = Path(raw_path)
    print(f"Path(raw_path): {abs_path}")
    print(f"repo_root: {repo_root}")

    try:
        normalized = uri_to_relpath(raw_uri, repo_root)
        print(f"归一化后: {normalized!r}")
        assert normalized == "lib.py", f"应该等于 'lib.py',实际是 {normalized!r}"
        print("通过")
    except Exception as e:
        print(f"失败: {type(e).__name__}: {e}")
