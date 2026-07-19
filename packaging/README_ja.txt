Apple Music Controller for Windows
===================================

Windows 版 Apple Music の再生音のキー(Transpose)とピッチをリアルタイムに
変更するツールです。処理は Apple Music の音声だけに掛かり、PC 上の他の音は
一切影響を受けません。再生中の曲の表示・シークバー・曲送り操作もできます。

プロジェクトページ: https://github.com/frogmagical/applemusic-controller


動作要件
--------
* Windows 10 (2004) 以降 / Windows 11
* Apple Music アプリ(Microsoft Store 版)
* 仮想オーディオケーブルドライバ。例: VB-CABLE(無料)
  https://vb-audio.com/Cable/
  管理者権限でインストールし、一度再起動してください。
  (再生側/録音側が対になった仮想デバイスなら他製品でも動作します)


使い方
------
1. 任意の場所に解凍し AppleMusicController.exe を実行
   (未署名のため SmartScreen の警告が出る場合があります。
    「詳細情報」→「実行」を選んでください)
2. Apple Music で再生を開始
3. アプリ画面で以下を設定:
   - Capture  : 仮想ケーブルの録音側(例: CABLE Output)。
                検出できた場合は自動選択されます
   - Output   : 実際に聴くスピーカー/ヘッドホン
   - 「Route Apple Music to the capture cable」にチェック
     → Apple Music の音が仮想ケーブルへ流れます。
     チェックを外すと Windows の既定値に戻ります
     ※ 変更は「次の曲」の再生開始から反映されます。切り替えたら曲を
        一度送ってください。設定は保存されるため、以後は Apple Music を
        再起動しても維持されます
   - 「Start processing」を押す
4. スライダーを操作:
   - Transpose : キー変更(±12 半音)
   - Pitch     : 微調整(±100 セント)
   シークバーと ⏮ ⏯ ⏭ ボタンで Apple Music を操作できます。


注意・制限事項
--------------
* テンポ(再生速度)変更はありません。Apple Music は DRM 保護された
  ストリームで音声を実時間でしか取り出せないため、ライブソースの
  加速再生は原理的に実現できません。
* 全体の遅延は約 150ms です。音楽鑑賞には問題ありませんが、
  映像との同期が必要な用途には向きません。
* シークとルーティングは非公開の仕組みに依存しており、Apple Music や
  Windows の大型アップデートで動かなくなる可能性があります。
* シークバーの操作には Apple Music のウィンドウが開いている必要があります。


本パッケージは pylibrb 経由で Rubber Band Library (GPL) を同梱しています。
ソースコード: https://github.com/frogmagical/applemusic-controller
