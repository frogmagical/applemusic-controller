# applemusic-controller

Windows 版 Apple Music の再生音に対して、**キー(Transpose)・ピッチ(Pitch)・テンポ(Speed)** をリアルタイムに変更する Python 製アプリです。処理は Apple Music の音声だけに掛かり、他のアプリの音声には影響しません。再生中の曲名・アーティスト・再生位置の表示と、再生/一時停止・曲送りの操作もできます。

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

- **再生情報・トランスポート操作**: Windows の SMTC (GlobalSystemMediaTransportControlsSession) API
- **音声処理**: [Rubber Band Library](https://breakfastquay.com/rubberband/) R3 エンジン([pylibrb](https://pypi.org/project/pylibrb/) バインディング)。リアルタイムモードで `process` 呼び出しをまたいで解析状態が維持されるため、ストリーミング処理でも劣化しません(Rubber Band は GPL ライセンスである点に注意)
- **音声入出力**: WASAPI (sounddevice)

## 動作要件

- Windows 10 2004 以降 / Windows 11
- Python 3.10 以降
- Apple Music (Microsoft Store 版)
- 仮想オーディオケーブル(いずれか 1 つ)
  - [VB-CABLE](https://vb-audio.com/Cable/)(推奨・無料。インストールに管理者権限が必要)
  - Voicemeeter、その他「出力デバイス+対になるキャプチャデバイス」を提供するもの

## セットアップ

1. **仮想オーディオケーブルの導入**(未導入の場合)

   [VB-CABLE](https://vb-audio.com/Cable/) をダウンロードし、管理者権限でインストールして再起動します。

2. **本アプリのインストール**

   ```powershell
   git clone https://github.com/frogmagical/applemusic-controller.git
   cd applemusic-controller
   py -3 -m venv .venv
   .venv\Scripts\python -m pip install -e .
   ```

3. **Apple Music の出力先を仮想ケーブルに変更**

   Windows の「設定 → システム → サウンド → 音量ミキサー」を開き、
   Apple Music の出力デバイスを **CABLE Input**(VB-CABLE の場合)に変更します。
   (`ms-settings:apps-volume` を実行すると直接開けます)

   > この設定により Apple Music の音は仮想ケーブルにだけ流れ、
   > 他のアプリの音は通常どおりスピーカーから出ます。

4. **起動**

   ```powershell
   .venv\Scripts\python -m amc
   ```

   GUI で以下を設定して **Start processing** を押します。

   - **Capture**: 仮想ケーブルのキャプチャ側(例: `CABLE Output (VB-Audio Virtual Cable)`)。既知の仮想ケーブルは自動選択されます
   - **Output**: 実際に音を出したいスピーカー/ヘッドホン

## 使い方

| コントロール | 範囲 | 説明 |
|---|---|---|
| Transpose | ±12 半音 | キー変更(カラオケのキー変更と同じ)。テンポは変わりません |
| Pitch | ±100 セント | 半音未満の微調整(A=440Hz ↔ 442Hz 合わせなど) |
| Speed | 50–150 % | テンポ変更。ピッチは変わりません(下記の制約あり) |
| ⏮ ⏯ ⏭ | — | Apple Music の曲送り / 再生・一時停止 |

## 既知の制約

- **Speed(テンポ)はライブソースの原理的制約があります。** Apple Music は実時間でしか音を出さないため:
  - **100% 超**: 入力が追い付かず、バッファが尽きると短い無音ギャップが入ります
  - **100% 未満**: 入力バッファが溜まり続けるため、上限(既定 5 秒)に達すると古い音声をスキップして追い付きます
  - キー/ピッチ変更(テンポ 100% のまま)にはこの制約はありません
- **レイテンシ**: DSP と バッファリングで合計 150ms 前後の遅延があります。音楽鑑賞では気になりませんが、映像との同期が必要な用途には不向きです
- **アルバム名の表示**: Apple Music は SMTC のアルバム欄を使わず、アーティスト欄に「アーティスト — アルバム名」形式で報告してくるため、本アプリ側で分解して表示しています
- 大きなピッチ変更(±6 半音以上)では音質劣化が知覚できる場合があります

## 開発

```
src/amc/
├── smtc.py      # SMTC: 再生情報の取得・トランスポート操作
├── devices.py   # WASAPI デバイス探索・仮想ケーブル自動検出
├── dsp.py       # Rubber Band ラッパー(キー/ピッチ/テンポ)
├── pipeline.py  # キャプチャ → DSP → 出力 のストリーミング
├── gui.py       # tkinter GUI
└── __main__.py  # `python -m amc` エントリポイント
```

再生情報だけを確認するには:

```powershell
.venv\Scripts\python -m amc.smtc
```
