from __future__ import annotations

import os

from ygo_effect_dsl.runtime_imports import current_checkout_environment


# Every subprocess spawned by tests must import the same checkout as pytest.
os.environ.update(current_checkout_environment())
