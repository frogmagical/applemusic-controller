Apple Music Controller for Windows
===================================

Windows 版 Apple Music の再生音のキー(Transpose)とピッチをリアルタイムに変更するツールです。
https://github.com/frogmagical/applemusic-controller

動作要件
--------
* Windows 10 (2004) 以降 / Windows 11
* Apple Music アプリ(Microsoft Store 版)
* 仮想オーディオケーブルドライバ。VB-CABLEは動作確認済みです。
  https://vb-audio.com/Cable/

使い方
------
1. 任意の場所に解凍し AppleMusicController.exe を実行
   (未署名のため SmartScreen の警告が出た場合、「詳細情報」→「実行」を選んでください)
2. Apple Musicを起動します
3. アプリ画面で以下を設定:
・Capture：仮想ケーブルを選択。(例: CABLE Output) 検出できた場合は自動選択されます
・Output：実際に聴くスピーカー/ヘッドホンを選択
・「Route Apple Music to the capture cable」にチェック
※チェックを外すとApple Musicの音声出力先が既定値に戻ります
・「Start processing」を押す

4. 好きな曲を再生
もし音が聞こえない場合、一度曲を停止した後に別の曲を再生してみてください

5. スライダーを操作:
Transpose : キー変更(±12 半音)
Pitch     : 微調整(±100 セント)
シークバーと ⏮ ⏯ ⏭ ボタンで直接曲を操作できます

注意・制限事項
--------------
個人作成アプリのため、Apple Musicのアップデートにより動作しなくなる恐れがあります

本パッケージは pylibrb 経由で Rubber Band Library (GPL) を同梱しています。
ソースコード: https://github.com/frogmagical/applemusic-controller
