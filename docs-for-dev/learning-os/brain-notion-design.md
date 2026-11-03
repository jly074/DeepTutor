> 2026-11-03：第一個唯讀來源快照切片已實作，見 [實作狀態與限制](notion-readonly.md)。本文件其餘內容仍為設計；真實 Notion 未連接，完整中樞與雙向同步未完成。

# 大腦資訊庫與 Notion 投影：設計提案

狀態：**設計未實作、模擬未跑、真實 Notion 未連接**。本文件只根據當前 checkout
盤點，不包含私人工作包或真實 Notion 內容。舊 Notion schema、Topic 欄位、歷史成績、
現行收課規則尚未取得，均待使用者允許的結構資料對照；沒有宣稱已映射或遷移。

## 使用者會看到什麼

v3 網站顯示任務、目標、規則、來源及學習證據；Notion 顯示允許分享的簡短摘要。
例如「合成單元 A 複習」有同一個任務編號：網站可查目前進度、一次錯答證據與下一步；
Notion 可看摘要與成果連結、提出更正，但不能直接把尚未驗收的任務標為正式完成。
dot 以相同任務編號回報，網站仍可獨立續作。同步失敗不等於原任務失敗。

「大腦」是現有服務的統一查詢及受控更新介面，不是再建立一套任務／記憶主資料庫。
v3 是正式資料的系統權威；本機限定內容的正式副本仍留本機，不能為集中管理而上雲。

## 當前可復用與缺口

| 範圍／實際位置 | 可復用 | 缺口／建議最小修改 | 驗收 | 需要批准 |
|---|---|---|---|---|
| `services/task_board.py` | SQLite cards、穩定 task id、workspace、due_date、archive、board revision、session links | 目前 status 只有 todo/doing/done，缺等待批准／本機／驗收及期限來源；先投影原狀態，不能偽稱完整任務引擎 | 同一 task id 重整仍一致；done 不被轉述為已掌握 | 合成讀取不需外部批准；真實摘要外送需批准 |
| `services/learning_journal/models.py`、`store.py` | LearningMission、LearningRecord、last_session；既有 JSON 版本檢查、路徑解析 | Mission 非完整 Goal 模型；跨任務 goals、期限來源、證據引用仍需增量欄位與遷移 | 原 journal 可讀；摘要明示不是原證據 | 規則與敏感內容外送依範圍批准 |
| `learning/models.py` | LearningEvidence 的 evidence_id/question_id/knowledge_point_id、result、來源、session/turn；TopicSource、MasteryTopic | evidence_id 可為空，舊資料不能直接作外部去重鍵；來源版本及答案衝突需補證據契約 | 空 ID 待修復，不猜年份；疑義不直接算錯 | 真實成績摘要公開範圍需批准 |
| `services/memory/store.py` | MemoryStore 的分層文件／事件、編輯操作、trace、按使用者路徑解析 | 尚無已證實的統一 Rule 版本／批准／取代契約；加結構化索引或 sidecar，原文仍由現有 store 管理 | 更正影響下一次讀取，舊版可追溯，刪除不留檢索副本 | 敏感記憶與外送先批准 |
| `services/workspace/context.py`、`models.py` | 帳戶及工作區解析、scope 驗證 | 同步映射也須完整綁 owner/workspace/destination | 跨帳戶與工作區不可查到他人映射 | 真實目的地與資料邊界需批准 |
| `learning/models.py:TopicSource`、`services/drive_source/` | 來源引用；Drive metadata-only 標記與不可讀保護 | 不代表下載教材；統一來源版本／隱私標記仍需增量補足 | Notion 摘要不能把 metadata-only 稱作已讀教材 | 檔名本身可能敏感，需明確允許 |
| Notion adapter | 搜尋 `deeptutor`、`scripts`、`web/lib` 未找到專用同步 adapter；只有泛用 MCP/OAuth 能力與文字提及 | 不假設泛用 MCP 已授權 Notion；另設受控 adapter 契約，未設定即 blocked | 未設定不發網路請求 | Notion 登入、目的地分享、persistent access、外部寫入均尚未批准 |

## 欄位方向與權威

第一階段全為 **v3 → 本地預覽**。未來經批准才啟用 v3 → Notion；不先做任意雙向覆寫。
下表是後續契約提案，不是已存在的 Notion properties 或 API 保證。

| 資料 | 權威／方向 | Notion 編輯含義 |
|---|---|---|
| task_id、goal_id、evidence_id、rule_id、source_ref、版本 | v3，單向摘要 | 不接受直接改 ID／版本；發現改動標 conflict |
| 任務標題、正式狀態、完成條件、成果連結 | v3 → Notion | Notion 的更正欄位只成提案；v3 驗證後更新再投影 |
| 截止日期與依據、固定／彈性分類 | v3 → Notion | 日期更正為提案；不直接改 Calendar，固定約定仍受保護 |
| 學習結果、弱點摘要、掌握推估與證據數 | v3 → Notion | 不允許 Notion 任意改分數／掌握；更正需連結證據 |
| 規則內容／適用範圍／批准狀態／被哪版取代 | v3 → Notion 的允許摘要 | 可提出 change proposal，未批准不影響正式規則 |
| 個人備註、修正建議、建議優先級 | 未來 Notion → v3 proposal inbox | 保留作者／時間／原版依據；不直接成正式任務狀態 |
| 同步狀態／最後核對時間／錯誤摘要 | v3 同步 ledger → Notion/UI | 系統管理，使用者不以改文字重置成功狀態 |

不開放同一個欄位兩端直接寫。未來接受提案時，v3 仍是正式值的唯一寫入者。
舊系統是否仍寫入目的地必須先確認；切換前逐項列出舊任務、觸發條件、接任者、
產物與回復方法。停用中的歷史自動化不自動恢復。

## ID、版本、去重與衝突

新增同步 ledger 放在現有帳戶持久層（建議 task board SQLite 的增量表，待實作審查），
只存映射／操作狀態，不複製 tasks/evidence/rules 主資料。映射鍵建議為
`(owner, workspace, entity_type, entity_id, destination_id)`；外部 page ID 是對照值，
不是正式 task id。顯示可讀 task id 供網站、Notion、dot 使用，不能拿任務編號當授權。

每個投影保存 payload_schema_version、local_revision／內容 hash、
last_verified_remote_hash、last_synced_at。現有 board revision 是整個看板版本，
不能冒充每筆 card revision；首輪可用 board revision 加 canonical card hash。
學習證據若沒有穩定 ID，先在原 store 做一次可追溯修復或標 pending，不能用摘要文字猜 ID。

操作鍵建議為 `(mapping_key, local_revision/hash, action)`。同版重複產生只留一個 outbox
操作；單一 writer 或租約序列化同一 mapping。這是本地避免重複機制，**不宣稱外部 API
恰好一次**。遠端出現多個同 entity id 項目時標 duplicate/conflict，不自動刪除。

寫前比較上次讀回 hash。遠端管理欄位變更或提案基於舊版時標 conflict，顯示兩版差異，
不採最後寫入者勝出。Notion 若沒有可用 compare-and-swap，讀寫間仍可能競爭：
寫後讀回只能偵測一部分衝突，故管理欄位約定單一 writer，不能宣稱完全消除競爭。

## 刪除、授權與失敗

本地 archive 投影為封存狀態，不刪正式學習證據。Notion 頁面被刪／封存表示
remote_missing，不能推論 v3 任務刪除；暫停同步並請使用者選恢復或解除映射。
正式刪除記憶須另有刪除請求，處理索引、衍生摘要、外部投影與備份保留政策；
完成狀態應列出哪些副本仍待清除，不能只刪一行就宣稱全面忘記。

未來外部寫入程序：

1. 驗證帳戶／workspace／目的地白名單、資料分類與該版 payload 的批准；先呈現具體差異。
2. 保存 operation id、版本/hash、目標與 pending 狀態；再做寫前讀取／衝突檢查。
3. 在已批准範圍寫入，讀回必要欄位與映射，核對一致才標 verified。
4. 逾時標 outcome_unknown，先依既有 page ID／穩定標記對帳；不盲目重建。
5. 找不到不能立即當作未執行：考慮權限與可見性延遲；有限次對帳仍不明就等待人工確認。
6. 未執行且可安全重試才有限退避重試；401/403 等待授權，429 等待重試時機。
   通知失敗只重送通知，不重跑成功外部寫入。重啟後仍保留批准與結果未知狀態。

顯示狀態：not_configured、preview_only、waiting_approval、queued、syncing、verified、
offline、waiting_local、conflict、outcome_unknown、blocked。這是擬議狀態，不是目前已實作。
離線可繼續本地任務；敏感來源缺本機時等待本機。同步狀態與任務狀態分開。

## 隱私與 dot 交接

敏感原文、檔名／路徑、OCR、圖片、embedding、trace、備份及識別對照留在本機。
向 Notion／雲端／模型／dot 僅輸出經允許的欄位白名單摘要；未知分類預設不外送。
Notion 的閱讀摘要也屬外送，不能因為是個人帳號就視為可放私人原文。
不要在錯誤、outbox 或測試快照保存 token、全文或含秘密的 URL。

交接 envelope 建議：task_id、workspace 的允許別名、任務版本、狀態、下一步、
截止依據摘要、來源／成果的授權連結、驗收結果。dot 只用同一 task_id 查詢／回報；
不能自行複製另一正式任務，不能因入口文字宣稱成功就修改為完成。
網站在 dot 不可用時仍能查正式任務。ChatGPT connector 不作產品 credentials。

## 建議下一輪：一筆任務的本地 Notion 投影預覽

推薦只做「現有 task card → 白名單摘要 → 本地投影預覽／模擬 ledger」：
選一個合成 task，沿用既有 id，產生擬議 Notion row JSON，顯示 preview_only。
不實作真實 adapter，不同步完整 memory/evidence，不建立第二份 task 主資料庫。

擬驗收：同版重試不新增；重啟映射仍在；更改 title 後只更新同 id；模擬遠端修改
進 conflict；模擬逾時成功後先讀回、不新增第二筆；跨 workspace 拒絕；
合成敏感欄位不進 payload/log；Notion 刪頁不刪 v3 task；完成看板卡不推導掌握。
這些測試本輪**尚未執行**。真正外部 API 形狀、限制、權限 scope 和 OAuth 流程
在獲准整合時查官方文件及帳戶條件，不能用此設計當作已驗證供應商契約。

下一輪本地合成流程可依另行開發指令進行；真實舊 schema 讀取需授權範圍，
真實 Notion 登入／持續存取、目的地、可外送欄位及寫入／遷移／單一 writer 切換
均需對應批准。本輪沒有執行這些動作。
