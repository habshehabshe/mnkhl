#!/usr/bin/env python3
"""mnkhl — deterministic context dumps for LLM chats.

From the Arabic منخل (sieve): the user decides what passes through.

Usage:
  mnkhl <view>          write .mnkhl/<view>.dump.md
  mnkhl <view> --stdout print to stdout instead of writing
  mnkhl init            create .mnkhl/ with a default view
  mnkhl --list          list available views

Views are plaintext files at .mnkhl/<name> (no extension).
Each line is one directive:

  [SRC-TREE]            emit the full source tree
  [SRC-TREE] (git-ignore)  emit the tree with .gitignore applied

Tokens are square-bracketed; options are parenthesized directly
after the token. The same token may appear on any number of
lines. Unknown tokens are hard errors — a typo must fail loudly.
"""

import re
import shutil
import subprocess
import sys
from pathlib import Path

VERSION = "0.01"
FENCE = "````"  # 4 backticks: content may contain 3-backtick blocks


def die(msg):
    print(f"mnkhl: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------

def repo_root():
    try:
        out = subprocess.run(["git", "rev-parse", "--show-toplevel"],
                             capture_output=True, text=True, check=True)
        return Path(out.stdout.strip())
    except subprocess.CalledProcessError:
        die("not inside a git repository")


def git_tracked(root):
    out = subprocess.run(["git", "ls-files"], cwd=root,
                         capture_output=True, text=True, check=True)
    return set(out.stdout.splitlines())


# ---------------------------------------------------------------------------
# View parsing
# ---------------------------------------------------------------------------

# One line = optional whitespace, [TOKEN], optional " (options)",
# optional "  # comment". Tokens are [A-Z-]; options are free text
# inside parens (no nesting).
LINE_RE = re.compile(
    r"^\s*"                                   # leading whitespace
    r"\[(?P<token>[A-Z][A-Z-]*)\]"            # [TOKEN]
    r"(?:\s*\((?P<options>[^()]*)\))?"        # optional (options)
    r"(?:\s*#\s*(?P<comment>.*))?$"           # optional # comment
)


def parse_view(text, view_name):
    """Parse view text into a list of (token, options, comment).

    Blank lines and lines that are only a comment are skipped.
    Anything else that does not match the grammar is a hard error.
    """
    entries = []
    for lineno, raw in enumerate(text.splitlines(), 1):
        m = LINE_RE.match(raw)
        if not m:
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            die(f"{view_name}:{lineno}: cannot parse line: {raw.strip()!r}")
        entries.append((m.group("token"), m.group("options"), m.group("comment")))
    return entries


# ---------------------------------------------------------------------------
# Token implementations
# ---------------------------------------------------------------------------
# Each token is a function (root, options, comment) -> list of lines.
# Register new tokens by adding an entry here. options is a string or
# None; comment is a string or None.

TOKENS = {}


def token(name):
    def register(fn):
        TOKENS[name] = fn
        return fn
    return register


def emit_header(out, title, comment):
    out.append(f"## {title}")
    if comment:
        out.append(f"*{comment}*")
        out.append("")


@token("SRC-TREE")
def token_src_tree(root, options, comment):
    """Emit the source tree.

    Options:
      git-ignore — apply .gitignore (use `tree` with its default
                   ignore behavior)
      (none)     — full tree, no filtering
    """
    out = []
    emit_header(out, "source tree", comment)
    cmd = ["tree"]
    if options and options.strip() == "git-ignore":
        # tree respects .gitignore only via -I patterns; the cleanest
        # equivalent is listing tracked files and building the tree
        # from them, but for 0.01 we shell out with an explicit
        # ignore of common litter plus git-ignored dirs is NOT
        # derivable from tree alone. Use git ls-files instead.
        pass
    if options and options.strip() == "git-ignore":
        tracked = git_tracked(root)
        out.append(FENCE)
        out.append(render_tree(tracked))
        out.append(FENCE)
        out.append("")
        return out
    result = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    if result.returncode != 0:
        die(f"tree command failed: {result.stderr.strip()}")
    out.append(FENCE)
    out.append(result.stdout.rstrip("\n"))
    out.append(FENCE)
    out.append("")
    return out


def render_tree(paths):
    """Render sorted relative paths as a directory tree, tree-style."""
    root = {}
    for p in sorted(paths):
        node = root
        for part in Path(p).parts:
            node = node.setdefault(part, {})
    lines = []

    def walk(node, prefix):
        items = list(node.items())
        for i, (name, child) in enumerate(items):
            last = i == len(items) - 1
            lines.append(prefix + ("└── " if last else "├── ") + name)
            walk(child, prefix + ("    " if last else "│   "))

    walk(root, "")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Dump assembly
# ---------------------------------------------------------------------------

def build_dump(root, view_name):
    view_path = root / ".mnkhl" / view_name
    if not view_path.is_file():
        views = sorted(p.name for p in (root / ".mnkhl").glob("*")
                       if p.is_file() and not p.name.endswith(".dump.md"))
        listing = "\n".join(f"  {v}" for v in views) or "  (none)"
        die(f"no such view: {view_name}\navailable views:\n{listing}")

    out = [f"# mnkhl dump: {view_name}", ""]
    for token_name, options, comment in parse_view(view_path.read_text(), view_name):
        if token_name not in TOKENS:
            die(f"unknown token [{token_name}] in view {view_name}")
        out.extend(TOKENS[token_name](root, options, comment))
    return "\n".join(out).rstrip() + "\n"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init(root):
    mnkhl_dir = root / ".mnkhl"
    mnkhl_dir.mkdir(exist_ok=True)
    view = mnkhl / "view"
    if view.exists():
        print(f"mnkhl: .mnkhl/view already exists — leaving it alone")
        return
    view.write_text(DEFAULT_VIEW)
    print("mnkhl: created .mnkhl/view")


DEFAULT_VIEW = """# default view — edit me
# One directive per line: [TOKEN] (options)  # comment

[SRC-TREE]
"""


def to_clipboard(text):
    for cmd in (["wl-copy"], ["xclip", "-selection", "clipboard"], ["pbcopy"]):
        if shutil.which(cmd[0]):
            subprocess.run(cmd, input=text, text=True)
            return
    die("no clipboard tool found (wl-copy, xclip, or pbcopy)")


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    if args[0] == "init":
        cmd_init(repo_root())
        return
    if args[0] in ("--list", "-l"):
        views_dir = repo_root() / ".mnkhl"
        if views_dir.is_dir():
            for v in sorted(views_dir.glob("*")):
                if v.is_file() and not v.name.endswith(".dump.md"):
                    print(v.name)
        return
    if args[0] in ("--version", "-v"):
        print(f"mnkhl {VERSION}")
        return

    view = args[0]
    root = repo_root()
    dump = build_dump(root, view)

    if "--stdout" in args:
        print(dump, end="")
    else:
        out_path = root / ".mnkhl" / f"{view}.dump.md"
        out_path.write_text(dump)
        print(f"wrote {out_path.relative_to(root)} ({len(dump.splitlines())} lines)")

    if "--clip" in args:
        to_clipboard(dump)
        print("copied to clipboard")


if __name__ == "__main__":
    main()
