# Windows 獨立開發試用與手動更新

本流程沿用 `scripts/update.py` 的 Git 工具與 `scripts/start_web.py` 啟動器；
不另建應用、不設定排程、不發布、不自動登入。適用來源固定為
`https://github.com/jly074/DeepTutor.git`。這是開發試用，不是正式服務部署。

## 發布前提（目前仍受阻）

2026-11-02 唯讀 `git ls-remote --heads origin` 顯示遠端僅有 `main`，
HEAD 為 `f7aed0744c36c5afef16a4261c31ebee1208cac2`。第一輪 `a8fb61400`、
第二輪 `93f952439` 與本文件所在第三輪尚未 push。
**現在 clone main 不會取得這三輪功能。** 需另行批准發布到指定試用分支，
建議名稱 `learning-os-trial`；名稱只是建議，尚未建立遠端分支。
發布完成後應提供實際分支與完整 commit SHA，供下列操作核對。

## 明日準備

Windows 電腦安裝 Git、Python 3.12（支援 3.11–3.14）、Node.js 22 LTS，
能存取 GitHub、PyPI 與 npm。使用新的 checkout 與新的試用資料目錄；
只使用合成資料。不要複製正式 runtime、金鑰或教材，也不需要 Google 登入。
若私人 GitHub 倉庫要求登入，使用 Git 自己的登入機制，不在指令 URL 放 token。
不需改 PowerShell 執行政策；腳本是 Python。

## 首次取得（遠端發布之後）

在 PowerShell 依序執行，每一步成功才執行下一步。
將 `PUBLISHED_BRANCH` 改成已確認發布的分支，不能直接使用占位文字。
`DeepTutorTrial` 及 `DeepTutorTrialData` 必須是尚不存在的新路徑。

```powershell
cd $env:USERPROFILE
git clone --single-branch --branch PUBLISHED_BRANCH https://github.com/jly074/DeepTutor.git DeepTutorTrial
cd DeepTutorTrial
py -3.12 scripts/learning_trial.py setup --branch PUBLISHED_BRANCH --home "$env:USERPROFILE\DeepTutorTrialData"
py -3.12 scripts/learning_trial.py status
py -3.12 scripts/learning_trial.py deps
py -3.12 scripts/learning_trial.py start
```

`status` 顯示完整 commit、分支與試用資料位置；應與交付 SHA 相符。
`deps` 在試用資料目錄的 `venv` 安裝既有 Python requirements，執行 pip check，
並在 checkout 的 `web` 執行 `npm ci --legacy-peer-deps`。會下載套件，可能耗時。
成功後才保存對應 commit 的依賴完成標記；失敗不能直接 start。
`start` 沿用現有開發啟動器，顯示實際啟動網址並維持前景運行；Ctrl+C 停止。
這個網址在使用者的 Windows 本機開啟，不是雲端預覽網址。
不會自動配置模型或 Drive；缺少模型時只驗收無模型的合成功能。

## 後續每輪更新

先在啟動視窗按 Ctrl+C，確認伺服器已停止。備份試用 runtime 後，在 checkout 執行：

```powershell
py -3.12 scripts/learning_trial.py update
py -3.12 scripts/learning_trial.py deps
py -3.12 scripts/learning_trial.py start
```

每一步成功才繼續。`update` 僅 fetch 指定分支並 fast-forward，輸出更新前後 SHA、
ahead/behind；沒有新版就明確顯示 Already up to date。其效果相當於受限制的
`git pull --ff-only`，實作分開 fetch 與本地 fast-forward，便於先檢查遠端版本。
它不安裝依賴、不重啟、不遷移資料。`deps` 與 `start` 是獨立步驟。
每次 commit 改變都要求重跑 deps；沒有新版且標記仍有效時可跳過 deps。

資料位於獨立 `DeepTutorTrialData/runtime`，更新程式不會碰它。
啟動新版程式可能執行應用既有的資料遷移，**Git 不保證資料向後相容**。
開始前停止伺服器並備份 runtime 至另一個本機目錄；備份可能含敏感設定，勿提交 Git。
回復時先保留失敗現場，另建舊版本 checkout 與相符的備份副本測試；
不要 reset/clean 現有 checkout，也不要用舊版直接開可能已遷移的唯一資料副本。

## 安全停止與下一步

| 情況 | 行為與下一步 |
|---|---|
| tracked 或 untracked 修改 | fetch 前停止；先 `git status --short`，保留並人工處理，不自動 stash/reset/clean。 |
| ignored 檔案將被新版覆蓋 | fast-forward 拒絕；保留檔案並人工處理。其他 ignored 檔案不移動。 |
| 本地自有 commit／分歧／切換錯分支 | 停止；交付 SHA 與 status 供核對，不 force。 |
| 離線、缺分支或無權限 | fetch 失敗，HEAD 不動；恢復連線／確認發布與登入後重試。 |
| 缺少 Python、Git、Node、npm | 安裝必要工具後重試；不代改系統設定。deps/start 檢查 Node 22。 |
| 依賴安裝失敗 | 無成功標記、start 受阻；修正安裝錯誤再跑 deps。程式更新可能已成功，沒有自動 rollback。 |
| lock 存在 | 可能仍在運行或異常結束；查 `.git/learning-trial.lock` PID，確認該試用流程已停止後才人工移除 lock。 |
| 開發伺服器產生 tracked 變動 | 一樣停止，不視為可丟棄。檢查 diff，交由開發者判定。 |

設定保存在該 checkout 的 `.git/learning-trial.json`；不接受任意來源 URL。
同一流程的 setup/update/deps/start 互斥。另行手動啟動的伺服器不在此 lock 管理內，
使用者仍須停止它們。OS／套件管理器環境仍沿用本機設定；不配置或輸出憑證。

## 三步驗收

1. 首次 clone 後跑 setup/status：版本等於已發布 SHA；資料路徑是新的試用目錄。
2. 跑 deps/start，開 Learning → Google Drive sources → 合成示範，保存一筆引用。
   預期標示模擬、metadata-only，沒有要求真實 Drive 登入。
3. Ctrl+C 停止，跑 update。無新版時顯示 Already up to date；有後續已發布版本時顯示
   新 SHA，再跑 deps/start，原合成引用應保留。可先建立 `trial-sentinel.txt` 再跑 update：
   預期安全停止且檔案內容不變；人工移到 checkout 外保留後才重試。

## 本輪驗證範圍

Linux 上以臨時本地 Git repositories 測試：乾淨 fast-forward、dirty/untracked、
ignored 碰撞、本地領先／分歧、遠端不可用、缺少遠端分支、沒有新版、版本辨識、
固定來源／分支、新 home 保護、runtime 保留、依賴失敗標記與啟動參數／lock。
啟動測試攔截 subprocess 呼叫，沒有在 fixtures 安裝依賴或啟動產品。
實際命令與結果：

```text
/workspace/.venvs/deeptutor/bin/python -m pytest tests/scripts/test_learning_trial.py tests/scripts/test_update.py tests/scripts/test_start_web.py -q
22 passed in 1.60s
/workspace/.venvs/deeptutor/bin/ruff check scripts/learning_trial.py tests/scripts/test_learning_trial.py
All checks passed!
```

連同既有 updater/start_web 測試執行，不宣稱全倉庫 full suite。

本環境沒有 Windows／PowerShell；Windows subprocess、npm.cmd、安裝相容性、
實機啟動與跨版本資料回復尚未驗收。雲端 Node 是 24，未另行安裝 Node 22 或
跑完整 deps。現有開發啟動器的實際應用驗證可參考前兩輪；不當作 Windows 證據。
