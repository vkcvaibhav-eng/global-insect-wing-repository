"""Generate the tracked synthetic demonstration PNG."""

from __future__ import annotations

from pathlib import Path

from wing_repository.demo_data import synthetic_wing_png


def main() -> None:
    destination = Path(__file__).resolve().parents[1] / "demo_data" / "sample_right_forewing.png"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(synthetic_wing_png())
    print(f"Generated {destination}")


if __name__ == "__main__":
    main()
