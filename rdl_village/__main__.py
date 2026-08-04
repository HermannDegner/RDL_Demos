"""実行エントリ。

    python -m rdl_village [ticks] [seed]

同じコード・初期状態・seed・tick数から同じsnapshotを得る（村§18）。
"""

import sys

from .simulation import VillageObserver, VillageSimulation


def main(argv):
    ticks = int(argv[0]) if len(argv) > 0 else 480
    seed = int(argv[1]) if len(argv) > 1 else 7
    simulation = VillageSimulation(seed=seed).run(ticks)
    observer = VillageObserver(simulation)
    print(observer.summary())
    print("\n--- 決定ログ例 ---")
    for row in observer.sample_decision_log(2):
        print(row)


if __name__ == "__main__":
    main(sys.argv[1:])
