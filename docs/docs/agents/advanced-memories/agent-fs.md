# Agent FS

`agent_fs` gives each agent its own **version-controlled file system**, backed by a git repository. Every write can be committed automatically, so the agent's files have a full history. The agent can diff, restore, revert, branch, tag and stash, just like a developer working with git.

Typical uses:

* a durable, auditable workspace for an agent's notes, plans, generated code or documents;
* letting an agent **experiment on a branch** and merge only what works;
* rolling a file back to the version that was known to be good.

---

## Installation

`agent_fs` is pure Python with no dependencies; it shells out to the `git` command-line tool, which must be installed. Requires Python ≥ 3.10.

The package lives in `agent-memories/fs`. Its `pyproject.toml` refers to a `README.md` that is not in the folder and uses an unusual build backend, so `pip install` may fail. In that case, put the folder on `PYTHONPATH`:

```bash
export PYTHONPATH=$PYTHONPATH:/path/to/agent-memories/fs
```

```python
from agent_fs import AgentFS
```

---

## Creating a File System

```python
fs = AgentFS("/var/lib/agents", subject_id="planner-agent",
             author_name="Planner Agent", author_email="planner@agents.local")
```

* The root is `<path>/<subject_id>` (here `/var/lib/agents/planner-agent`). It is created if missing.
* On first use, a git repository is initialised there with an empty initial commit, so `HEAD` is always valid.
* All paths passed to the API are **relative to that root**. A path that resolves outside the root (for example `../other-agent/x`) raises `AgentFSError`.

---

## Working with Files

```python
sha = fs.write("notes/plan.md", "# Plan\n- step 1\n")          # writes and commits
fs.write("notes/plan.md", "# Plan\n- step 1\n- step 2\n", message="add step 2")
fs.write("data/blob.bin", b"\x00\x01", auto_commit=False)      # write without committing

fs.read("notes/plan.md")            # str (UTF-8)
fs.read_bytes("data/blob.bin")      # bytes

fs.copy("notes/plan.md", "notes/plan-v2.md")
fs.move("notes/plan-v2.md", "archive/plan-v2.md")
fs.delete("archive/plan-v2.md")

fs.mkdir("reports/2026")
fs.exists("notes/plan.md")          # True
fs.is_dir("reports")                # True
fs.list()                           # top-level entries (excluding .git)
fs.list("notes", recursive=True)    # depth-first listing
```

`write`, `delete`, `move` and `copy` commit by default, returning the new commit hash. The default messages are `write: <path>`, `delete: <path>`, `move: <src> -> <dst>` and `copy: <src> -> <dst>`. Pass `auto_commit=False` to batch several changes into one commit:

```python
fs.write("a.txt", "A", auto_commit=False)
fs.write("b.txt", "B", auto_commit=False)
fs.stage()                          # git add -A (or fs.stage("a.txt", "b.txt"))
fs.commit("add a and b")
```

Missing files raise `AgentFSFileNotFoundError`.

---

## History and Diffs

```python
fs.head()                                   # current commit hash
for c in fs.log(limit=5):                   # newest first
    print(c.short_hash, c.date, c.message, c.files_changed)
fs.log(file_path="notes/plan.md")           # commits touching one file
fs.log(branch="experiment")

fs.status()                                 # [StatusEntry(path, staged, unstaged), ...]

fs.diff()                                   # unstaged changes
fs.diff(staged=True)                        # staged changes
fs.diff(from_ref="HEAD~1")                  # HEAD~1 vs HEAD
fs.diff(from_ref="main", to_ref="experiment", file_path="notes/plan.md")
```

`CommitInfo` has `hash`, `short_hash`, `author`, `email`, `date`, `message` and `files_changed`.

---

## Restoring and Undoing

```python
old = fs.read_at("notes/plan.md", "HEAD~2")      # content at any commit/branch/tag
raw = fs.read_bytes_at("data/blob.bin", "v1")

fs.restore("notes/plan.md", "HEAD~2")            # write the old content back (and commit)
fs.revert(commit_hash)                           # new commit undoing a commit
fs.cherry_pick(commit_hash)                      # apply a commit onto the current branch
fs.checkout("HEAD~1", file_path="notes/plan.md") # restore one file in the working tree
```

---

## Branches, Merges and Tags

```python
fs.create_branch("experiment")                   # from HEAD (or from_ref="v1")
fs.checkout("experiment")
fs.write("notes/plan.md", "# Experimental plan\n")
fs.checkout("master")                            # the default branch name depends on your git config
fs.merge("experiment", message="merge experiment")
fs.delete_branch("experiment")                   # force=True for unmerged branches

fs.branches()                                    # ["experiment", "master"]
fs.current_branch()
fs.checkout("hotfix", create=True)               # create and switch

fs.tag("v1")                                     # lightweight tag
fs.tag("v2", message="known-good plan")          # annotated tag
fs.tags()                                        # newest first
fs.delete_tag("v1")
```

`merge` raises `MergeConflictError` on conflicts. Branch errors raise `BranchError`, and an unknown ref passed to `checkout` raises `RefNotFoundError`.

---

## Stash

```python
fs.write("notes/wip.md", "half done", auto_commit=False)
fs.stage("notes/wip.md")   # new files must be staged; git stash ignores untracked files
fs.stash("work in progress")
fs.stash_list()        # [{"index": 0, "ref": "stash@{0}", "message": "On master: work in progress"}]
fs.stash_apply(0)      # apply, keep the entry
fs.stash_pop(0)        # apply and remove
fs.stash_drop(0)       # remove without applying
```

---

## Repository Summary

```python
fs.info()
# {"root": "...", "branch": "master", "head": "...", "branches": [...], "tags": [...], "status": [...]}
```

---

## Exceptions

All errors derive from `AgentFSError`:

| Exception | Raised when |
|---|---|
| `AgentFSFileNotFoundError` | A file to read, delete, move or copy does not exist |
| `CommitError` | A commit, revert or cherry-pick fails |
| `BranchError` | Creating or deleting a branch fails |
| `MergeConflictError` | A merge has conflicts |
| `RefNotFoundError` | A ref or path at a ref does not exist |
| `AgentFSError` | Any other git failure, or a path that escapes the root |

---

## API Reference

| Area | Methods |
|---|---|
| Files | `read`, `read_bytes`, `write`, `delete`, `move`, `copy`, `mkdir`, `exists`, `is_dir`, `list` |
| Commits | `stage`, `unstage`, `commit`, `head`, `status`, `log`, `diff` |
| Branches | `branches`, `current_branch`, `create_branch`, `delete_branch`, `checkout`, `merge` |
| Tags | `tag`, `tags`, `delete_tag` |
| Versions | `read_at`, `read_bytes_at`, `restore`, `revert`, `cherry_pick` |
| Stash | `stash`, `stash_pop`, `stash_apply`, `stash_drop`, `stash_list` |
| Info | `info` |
