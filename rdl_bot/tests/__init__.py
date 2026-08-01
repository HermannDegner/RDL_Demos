import os
import sys

# 単体ファイルを直接実行した場合でも rdl_bot/ 直下のモジュールを
# import できるようにする（unittest discover 経由なら不要だが無害）。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
