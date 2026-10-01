# GitGood

An interactive CLI tool that teaches GitHub Flow through hands-on simulation. Practice real `git` and `gh` commands in a virtual repository environment with structured lessons and real-time feedback.

## Features

- **Virtual Git Environment** - Practice without affecting real repositories
- **6 Progressive Lessons** - From branching basics to complete GitHub Flow
- **Real-Time Validation** - Immediate feedback with contextual hints
- **GitHub CLI Support** - Learn `gh` commands for pull request workflows
- **Rich Terminal UI** - Color-coded output, status panels, and commit tree visualization

## Installation

Requires Python 3.10 or higher.

```bash
# Clone the repository
git clone <repository-url>
cd github_learner_in_terminal

# Install the package
pip install -e .

# Or with development dependencies
pip install -e ".[dev]"
```

## Quick Start

```bash
# Launch the application
gitgood

# Or run as a module
python3 -m gitgood
```

Once inside GitGood:

```
$ lessons          # View available lessons
$ lesson 1         # Start the first lesson
$ help             # Show all available commands
$ status           # View repository status
$ tree             # View commit history
$ quit             # Exit the application
```

## Lessons

GitGood includes 6 structured lessons that build on each other:

| # | Lesson | What You'll Learn |
|---|--------|-------------------|
| 1 | **Creating and Switching Branches** | Create feature branches, switch between branches |
| 2 | **Making Commits** | Stage files, write commit messages, view history |
| 3 | **Pushing to Remote** | Push branches to GitHub, set up tracking |
| 4 | **Creating Pull Requests** | Create and manage PRs with `gh` CLI |
| 5 | **Code Review Process** | Respond to feedback, update PRs |
| 6 | **Merging and Cleanup** | Merge PRs, sync local repo, delete branches |

Each lesson unlocks after completing its prerequisites.

## Supported Commands

### Git Commands

**Branching**
```bash
git branch                    # List branches
git branch <name>             # Create a branch
git branch -d <name>          # Delete a branch
git checkout <branch>         # Switch to a branch
git checkout -b <branch>      # Create and switch to a branch
git switch <branch>           # Switch to a branch (modern)
git switch -c <branch>        # Create and switch (modern)
```

**Staging & Committing**
```bash
git status                    # Show repository status
git add <file>                # Stage a file
git add .                     # Stage all changes
git commit -m "message"       # Create a commit
git commit --amend            # Amend the last commit
```

**History**
```bash
git log                       # Show commit history
git log --oneline             # Abbreviated history
git diff                      # Show unstaged changes
git diff --staged             # Show staged changes
```

**Remote Operations**
```bash
git remote -v                 # Show remotes
git push                      # Push to remote
git push -u origin <branch>   # Push with upstream tracking
git pull                      # Pull from remote
git fetch                     # Fetch from remote
```

**Merging**
```bash
git merge <branch>            # Merge a branch
git reset                     # Reset changes
```

### GitHub CLI Commands

```bash
gh pr create --title "..." --body "..."   # Create a pull request
gh pr list                                 # List pull requests
gh pr view [number]                        # View PR details
gh pr merge [number]                       # Merge a pull request
gh pr close <number>                       # Close a pull request
```

### Application Commands

```bash
help                          # Show command help
help <command>                # Help for a specific command
lessons                       # List available lessons
lesson <number>               # Start a lesson
hint                          # Get a hint for current step
skip                          # Skip current step (debugging)
status                        # Show status panel
tree                          # Show commit tree
quit                          # Exit the application
```

## How It Works

GitGood simulates a complete Git environment in memory:

- **Virtual Repository** - Tracks branches, commits, staging area, and working changes without touching your filesystem
- **Simulated GitHub** - Handles pull request operations locally
- **Command Parser** - Interprets git/gh commands and executes them against the virtual repository
- **Lesson Engine** - Validates your commands against expected patterns and provides progressive hints

### Lesson Flow

1. **Read the instruction** - Each step explains what to do
2. **Type the command** - Enter the git/gh command
3. **Get feedback** - Success message or helpful hints
4. **Progress** - Move to the next step automatically

If you get stuck, type `hint` for suggestions.

## Development

### Running Tests

```bash
pytest
pytest --cov=src/gitgood tests/    # With coverage
```

### Linting & Type Checking

```bash
ruff check src/ tests/             # Lint
ruff check --fix src/ tests/       # Auto-fix
mypy src/gitgood                   # Type check
```

### Project Structure

```
src/gitgood/
├── app.py              # Main application
├── core/               # Virtual repository & GitHub simulation
├── parser/             # Command parsing & execution
├── lessons/            # Lesson engine & YAML data files
└── ui/                 # Terminal interface (Rich/prompt-toolkit)
```

## Dependencies

- [Rich](https://rich.readthedocs.io/) - Terminal UI rendering
- [prompt-toolkit](https://python-prompt-toolkit.readthedocs.io/) - Interactive command prompt
- [PyYAML](https://pyyaml.org/) - Lesson file parsing
- [Pydantic](https://docs.pydantic.dev/) - Data validation

## License

MIT

---

Built by [@ethanarnold](https://github.com/ethanarnold) with [Claude Code](https://claude.ai/code)
