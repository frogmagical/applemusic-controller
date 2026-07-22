# applemusic-controller

Windows 版 Apple Music の楽曲の、**キー(Transpose)・ピッチ(Pitch)** を変更するアプリです。  
再生中の曲名・アーティスト・再生位置の表示と、再生/一時停止・曲送りの操作もできます。

## 仕組み

Apple Music アプリ自体にはキー/ピッチ変更機能が無いため、オーディオ経路上で処理します。

```
Apple Music ──(Windows のアプリ別出力設定)──▶ 仮想オーディオケーブル(入力側)
                                                      │
                     仮想ケーブル(キャプチャ側) ──▶ 本アプリ
                                                      │  Rubber Band (R3) による
                                                      │  ピッチシフト / タイムストレッチ
                                                      ▼
                                              実際のスピーカー
他のアプリの音声 ─────────(通常経路のまま)─────────▶ 実際のスピーカー
```

## ダウンロード(exe 版)

Python 環境が無くても使える単体 exe を同梱しています:

**[release/AppleMusicController-win64.zip](release/AppleMusicController-win64.zip)** 
([Direct Link](https://github.com/frogmagical/applemusic-controller/raw/main/release/AppleMusicController-win64.zip))

## 動作要件

- Windows 10 2004 以降 / Windows 11
- Python 3.10 以降
- Apple Music (Microsoft Store 版)
- 仮想オーディオケーブル
  - [VB-CABLE](https://vb-audio.com/Cable/)(未導入の場合推奨、動作確認済み)
  - Voicemeeter、その他「出力デバイス+対になるキャプチャデバイス」を提供するもの

## セットアップ

1. **仮想オーディオケーブルの導入**

   [VB-CABLE](https://vb-audio.com/Cable/) をダウンロードし、管理者権限でインストールして再起動します。

2. zipファイルを任意の場所で解凍し AppleMusicController.exe を実行

3. Apple Musicを起動します

4. アプリ画面で以下を設定:
  - Capture：仮想ケーブルを選択。(例: CABLE Output) 検出できた場合は自動選択されます
  - Output：実際に聴くスピーカー/ヘッドホンを選択
  - 「Route Apple Music to the capture cable」にチェック (チェックを外すとApple Musicの音声出力先が既定値に戻ります)
  - 「Start processing」を押す

5. 好きな曲を再生
もし音が聞こえない場合、一度曲を停止した後に別の曲を再生してみてください

6. スライダーを操作:
Transpose : キー変更(±12 半音)
Pitch     : 微調整(±100 セント)
シークバーと ⏮ ⏯ ⏭ ボタンで直接曲を操作できます

## 使い方

| コントロール | 範囲        | 説明                                                       |
| ------------ | ----------- | -----------------------------------------------------------|
| Transpose    | ±12 半音    | キー変更(カラオケのキー変更と同じ)。テンポは変わりません   |
| Pitch        | ±100 セント | 半音未満の微調整(A=440Hz ↔ 442Hz 合わせなど)               |
| シークバー   | —           | 曲内の再生位置を移動                                       |
| ⏮ ⏯ ⏭        | —           | Apple Music の曲送り / 再生・一時停止                     |
| Lyrics       | —           | 歌詞ウィンドウを表示。歌詞が見つからない曲ではグレーアウト |
| Route トグル | On/Off      | Apple Music の出力先切り替え                               |