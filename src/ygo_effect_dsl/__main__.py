"""Legacy DSL CLI entrypoint.

This CLI remains for compatibility while the repository transitions to the
ocgcore/EDOPro-driven engine path. It must not be treated as the game-tree
search engine runtime or as an action-generation source.
"""

from ygo_effect_dsl.cli.main import main

if __name__ == "__main__":
    raise SystemExit(main())
