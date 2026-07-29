# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import pytest

from agentkit.toolkit.config import (
    CloudStrategyConfig,
    CommonConfig,
    HybridStrategyConfig,
)
from agentkit.toolkit.strategies.cloud_strategy import CloudStrategy
from agentkit.toolkit.strategies.hybrid_strategy import HybridStrategy


@pytest.mark.parametrize(
    ("strategy", "strategy_config"),
    [
        (CloudStrategy(), CloudStrategyConfig(project_name="lh-test")),
        (HybridStrategy(), HybridStrategyConfig(project_name="lh-test")),
    ],
)
def test_runtime_project_name_is_forwarded_to_runner(strategy, strategy_config) -> None:
    runner_config = strategy._to_runner_config(CommonConfig(), strategy_config)

    assert runner_config.project_name == "lh-test"
