from __future__ import annotations

from pathlib import Path

import pandas as pd

from autonomous_investment_robot.services.ml.pipeline import train_model_from_csv


def test_train_model_pipeline_writes_artifact(tmp_path: Path) -> None:
    src = tmp_path / "features.csv"
    out = tmp_path / "model.pkl"
    df = pd.DataFrame(
        {
            "spread_bps": [1.0, 1.2, 0.8, 1.5],
            "imbalance": [0.1, -0.2, 0.05, 0.3],
            "edge_bps": [5.0, -3.0, 2.0, 7.0],
        }
    )
    df.to_csv(src, index=False)
    res = train_model_from_csv(str(src), str(out), target_col="edge_bps")
    assert Path(res.output_path).exists()
    assert res.rows == 4
