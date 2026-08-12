"""Where the documentation is.

The CLI's readers are people and the coding agents they hand this to,
and they need different URLs: a person wants the rendered site to browse,
an agent wants one self-sufficient page, as markdown. Both lines are
printed together — the reader ignores the one that is not theirs — so
neither audience has to guess a URL, and an agent never has to infer
that `/llms.txt` exists.
"""

# The rendered documentation site, for a person.
SITE = "https://docs.albus.sh"

# Albus in one page, written for a coding agent to execute: setup, the
# whole API surface, the rules, and examples. One page because an agent
# reads the URL it is given and rarely follows a link. Mintlify serves
# any page as markdown at `.md`.
AGENTS = "https://docs.albus.sh/agents/docs.md"

# What every error the CLI reports is documented under.
TROUBLESHOOTING = "https://docs.albus.sh/guides/troubleshooting"
