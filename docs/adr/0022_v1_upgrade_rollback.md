# ADR 0022: v1.0.0 upgrade and rollback qualification

## Status

Accepted for v1.0.0 production distribution qualification.

## Context

v1.0.0 does not ship an automatic updater. The release channel is manual wheel/sdist install for Python users and a manual Windows portable package for desktop users. Because the product uses external assets and user-owned caches, upgrade and rollback must keep package files separate from user cache/config/evidence.

## Decision

The v1.0.0 upgrade and rollback matrix is:

| id | path | required evidence |
| --- | --- | --- |
| clean_install | install wheel in a clean virtual environment or extract the portable package into a clean directory | CI clean venv smoke and Windows executable smoke |
| 0.5_to_1.0_upgrade | keep the previous install/package, back up user cache/config/evidence, then install or extract v1.0.0 into a clean package location | manual upgrade instructions and pre-migration backup requirement |
| 1.0_patch_upgrade | keep the previous v1.0.x package, then install or extract the patch package into a clean package location | same clean install smoke plus manual rollback path |
| rollback | delete the current package directory or uninstall the current wheel, then restore the previous package or reinstall the previous wheel | previous package or wheel must be retained before upgrade |
| uninstall_reinstall | remove package files only, then reinstall into a clean package location | user cache/config/evidence stays outside the package directory |
| offline_runtime | run without bundled WebView2, ocgcore, CardScripts, BabelCDB, card images, or card text | runtime fails closed and assets are acquired only through the owned cache resolver |

The process must not depend on editable install. The parent/worker subprocess import source must be consistent: subprocesses use the same package environment as the parent, and checkout tests use `current_checkout_environment()` only to keep test subprocesses pinned to the active checkout. This is a test harness rule, not a production distribution dependency.

User cache/config/evidence must remain outside wheel, sdist, executable, installer, and portable package directories. A rollback-capable migration may proceed after validation. A migration that cannot be rolled back must require a pre-migration backup and explicit confirmation before modifying user cache/config/evidence. v1.0.0 currently avoids irreversible user-data migrations.

External assets are never bundled into release artifacts. ocgcore, CardScripts, BabelCDB, card images, and card text are resolved through the owned cache resolver and verified against lock evidence before use.

## Consequences

The production gate can reject a release when clean venv smoke, Windows executable smoke, manual rollback instructions, import-source consistency, or external asset isolation are missing.
