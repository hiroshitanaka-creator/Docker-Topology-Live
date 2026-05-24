# 🌐 Docker-Topology-Live
> **CUIの退屈な docker ps から、すべてのコンテナを解放せよ。**
> Docker-Topology-Live は、ローカルマシン内で自律的に蠢く Docker コンテナと仮想ネットワークの繋がりをリアルタイムにスキャンし、暗黒の宇宙空間（3D Force-Directed Graph）にネオン輝く立体トポロジーとして描き出す、開発者のためのデジタル・ツイン・ビューアです。
> 
## ⚡ 特徴（Core Features）
 * **🌌 究極の視覚的支配（3D WebGL Canvas）**
   Three.js（WebGL）による圧倒的に滑らかな3D空間。マウスのドラッグで回転、ホイールでズーム、コンテナを掴んで物理演算で引き剥がすような、直感的ハックが可能です。
 * **🔌 隠れた繋がりの可視化（Network Discovery）**
   デフォルトの bridge から自作のカスタムネットワーク、さらには複雑な docker-compose によって自動生成されたブリッジまでを瞬時にパース。どのコンテナが、どの「核（ネットワーク）」に属し、どのIPアドレスを持っているかを立体的に暴き出します。
 * **🛠️ 依存ゼロの超軽量アーキテクチャ**
   重厚なモニタリングツールは不要。ローカルの Python スクリプトと、ブラウザ標準の HTML/JavaScript だけで構成される、ハッカーライクでクリーンなインフラ設計。
## 🛠️ 技術スタック（The Stack）
| レイヤー | 使用技術 / ライブラリ | 役割 |
|---|---|---|
| **Backend** | Python 3.11+ / docker-py | ローカルの /var/run/docker.sock からトポロジー構造を抽出 |
| **Frontend** | JavaScript / 3d-force-graph (Three.js) | WebGLを用いた立体フォースディレクテッドグラフのリアルタイム描画 |
| **Data Contract** | Standard JSON | 点（Nodes）と線（Links）のミニマムなトポロジーデータ表現 |
## 🚀 クイックスタート（1分で起動）
### 1. 依存ライブラリのインストール
```bash
pip install docker

```
### 2. ローカル環境のスキャン
```bash
python app.py

```
> スキャンが成功すると、カレントディレクトリに topology.json が自律生成されます。
> 
### 3. 立体空間の起動
ローカルファイルをブラウザで安全に開くため、Pythonの簡易サーバーを起動します。
```bash
python -m http.server 8000

```
ブラウザで **http://localhost:8000** にアクセスすると、あなたのマシンに構築された独自の「Docker都市」がネオンの光となって出現します。
## 🗺️ ロードマップ：今後の進化（Future Roadmap）
 * [ ] **Phase 1: [MVP]** 静的JSONエクスポートと3D描画（★現在ココ）
 * [ ] **Phase 2: [Live Pulse]** Docker Event APIとWebSocket（FastAPI）を繋ぎ、コンテナの up/down をリロードなしでグラフへリアルタイム反映。
 * [ ] **Phase 3: [Metric Glow]** docker stats からCPU/メモリ消費量を毎秒ストリーミング。過負荷なコンテナノードがパルス状に赤く激しく明滅するエフェクトの実装。
> **"Your infrastructure is no longer just a list of texts. It's a living, breathing neon universe."**
