# Source: Flask 1.1.2, flask/cli.py, lines 864-896
# Used for syntactic parsing only — do not import or execute
import click
import os
import sys

with_appcontext = lambda f: f
pass_script_info = lambda f: f


@click.command("shell", short_help="Run a shell in the app context.")
@with_appcontext
def shell_command():
    """Run an interactive Python shell in the context of a given
    Flask application.  The application will populate the default
    namespace of this shell according to it's configuration.

    This is useful for executing small snippets of management code
    without having to manually configure the application.
    """
    import code
    from .globals import _app_ctx_stack

    app = _app_ctx_stack.top.app
    banner = "Python %s on %s\nApp: %s [%s]\nInstance: %s" % (
        sys.version,
        sys.platform,
        app.import_name,
        app.env,
        app.instance_path,
    )
    ctx = {}

    startup = os.environ.get("PYTHONSTARTUP")
    if startup and os.path.isfile(startup):
        with open(startup, "r") as f:
            eval(compile(f.read(), startup, "exec"), ctx)

    ctx.update(app.make_shell_context())

    code.interact(banner=banner, local=ctx)
